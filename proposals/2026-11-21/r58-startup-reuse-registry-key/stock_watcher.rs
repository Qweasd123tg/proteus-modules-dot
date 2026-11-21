impl HttpAppState {
    pub(super) async fn stock_new_for_workspace(
        server: AppServerHandle,
        cwd: PathBuf,
        shutdown: broadcast::Sender<()>,
        security: HttpSecurity,
    ) -> Self {
        let initial_server = server.clone();
        let launch = HttpLaunchContext {
            config: server.config.read().await.clone(),
            cwd,
            config_path: server.config_path.clone(),
            profile_was_present: server
                .config_path
                .as_ref()
                .is_some_and(|path| path.exists()),
            initial_session_dir: server.session_dir_path(),
        };
        let mut session_servers = HashMap::new();
        if let Some(session_dir) = server.session_dir_path() {
            session_servers.insert(session_key(session_dir), server.clone());
        }
        let (activity_events, _) = broadcast::channel(1024);
        let state = Self {
            launch: Arc::new(launch),
            storage: server.storage.clone(),
            session_lifecycle: Arc::default(),
            session_servers: Arc::new(Mutex::new(session_servers)),
            activity_events,
            watched_sessions: Arc::new(StdMutex::new(HashSet::new())),
            shutdown,
            security,
        };
        state.stock_watch_server(initial_server);
        state
    }

    pub(super) async fn stock_remember_server(&self, server: AppServerHandle) {
        if let Some(session_dir) = server.session_dir_path() {
            let key = session_key(session_dir.clone());
            self.session_servers
                .lock()
                .await
                .insert(key.clone(), server.clone());
            self.stock_watch_server(server);
            self.emit_session_activity_for_dir(&key).await;
        }
    }

    fn stock_watch_server(&self, server: AppServerHandle) {
        let Some(session_dir) = server.session_dir_path() else {
            return;
        };
        let session_dir = session_key(session_dir);
        {
            let mut watched = self
                .watched_sessions
                .lock()
                .expect("watched session lock poisoned");
            if !watched.insert(session_dir.clone()) {
                return;
            }
        }

        let state = self.clone();
        let mut events = server.subscribe();
        tokio::spawn(async move {
            loop {
                match events.recv().await {
                    Ok(event) => {
                        let should_stop = matches!(event, AppServerEvent::Shutdown);
                        if app_event_affects_session_activity(&event) {
                            state.emit_session_activity_for_dir(&session_dir).await;
                        }
                        if should_stop {
                            break;
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(_)) => {
                        state.emit_session_activity_for_dir(&session_dir).await;
                    }
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
        });
    }
}
