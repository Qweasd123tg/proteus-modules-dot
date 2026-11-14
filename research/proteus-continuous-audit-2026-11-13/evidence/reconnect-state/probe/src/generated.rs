// GENERATED from recorded production method bodies. Only visibility is relaxed.
impl WindowGroup {
pub fn set_core(&self, api: Api, backend: Option<BackendGuard>) {
        *self.0.borrow().core.lock().unwrap() = Some(CoreConnection { api, backend });
    }
pub fn has_core_connection(&self, connection: u64) -> bool {
        self.0.borrow().core.try_lock().ok().is_some_and(|core| {
            core.as_ref()
                .is_some_and(|core| core.api.connection_id() == connection)
        })
    }
pub fn core_slot(&self) -> Arc<Mutex<Option<CoreConnection>>> {
        self.0.borrow().core.clone()
    }
fn server_stopped(&self, connection: u64, report: &str, cx: &mut App) {
        let core = self.0.borrow().core.clone();
        {
            let Ok(mut current) = core.try_lock() else {
                return;
            };
            if current
                .as_ref()
                .is_none_or(|core| core.api.connection_id() != connection)
            {
                return;
            }
            current.take();
        }
        let views: Vec<_> = self
            .0
            .borrow()
            .windows
            .iter()
            .map(|(view, _)| view.clone())
            .collect();
        for view in views {
            view.update(cx, |this, cx| {
                if this
                    .api
                    .as_ref()
                    .is_none_or(|api| api.connection_id() != connection)
                {
                    return;
                }
                this.api = None;
                this.notice = Some(report.to_owned().into());
                // A Core failure cannot hide another driver's running turn or Stop.
                this.status = Status::Ready;
                cx.notify();
            })
            .ok();
        }
    }
}
impl Workspace {
pub fn open_chat(
        &mut self,
        key: ChatKey,
        open: OpenDocument,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if !self.begin_navigation(cx) {
            return;
        }
        if self.deleting_sessions.contains(&key) {
            return;
        }
        if self.open_catalog_subagent(&key, window, cx) {
            return;
        }
        self.creating_chat = None;
        let id = key.tab_id();
        if self.show_external_tab(&id, cx) {
            return;
        }
        let switched = self.select_chat_space(&key, cx);
        if let Some(root) = self.spaces.active_root().and_then(tabs::chat_key)
            && root != key
            && !self.chats.contains_key(&root.tab_id())
        {
            self.ensure_chat(root, window, cx);
        }
        // Re-entering an area restores its document/pane focus. A click on
        // the already displayed root still returns directly to that chat.
        if switched && self.spaces.active_root() == Some(id.as_str()) {
            if !self.layout.contains(&id) {
                self.show_tab(
                    &id,
                    OpenDocument {
                        preview: false,
                        focus: open.focus,
                    },
                    window,
                    cx,
                );
            }
            if !self.chats.contains_key(&id) {
                self.resume_key(key, None, window, cx);
            }
            self.focus_active(window, cx);
            return;
        }
        if self.chats.contains_key(&id) {
            self.show_tab(&id, open, window, cx);
            return;
        }
        // Selection belongs to the click, never to the order of RPC replies.
        // The shared pane already renders an unloaded chat as a loading page.
        self.show_tab(&id, open, window, cx);
        self.resume_key(key, Some(open), window, cx);
    }
fn insert_chat(&mut self, dir: PathBuf, window: &mut Window, cx: &mut Context<Self>) -> String {
        let id = tabs::chat(&dir);
        if self.chats.contains_key(&id) {
            return id;
        }
        let Some(api) = self.api() else {
            return id;
        };
        let extras = self.composer_extras(cx);
        let workspace = cx.weak_entity();
        let stream = self.startup_streams.remove(&dir);
        let view = cx.new(|cx| Chat::new(api, workspace, dir, stream, extras, window, cx));
        self.bind_chat(&id, view, cx);
        id
    }
pub fn sync_chats(&mut self, layout: &TabLayout, cx: &mut Context<Self>) {
        self.chats
            .retain(|id, _| self.spaces.contains(id) || self.spaces.roots().any(|root| root == id));
        self.release_hidden_chat_activities(layout, cx);
        // A load owns its subscription until its acknowledgement arrives.
        // A quick reopen must reuse it instead of registering the same thread
        // twice while the first result is still queued for the UI.
        let active = layout.active_chat(self.active_chat.as_deref());
        if active != self.active_chat {
            // Activity updates are taken from the active chat's stream; a
            // reload covers what arrived elsewhere meanwhile.
            if active.is_some() {
                self.notice = None;
                self.refresh_sessions(cx);
            }
            // Chats draw from their own cache; the composer icons move to
            // the new active one.
            for id in [&self.active_chat, &active].into_iter().flatten() {
                if let Some(chat) = self.chats.get(id) {
                    chat.view.update(cx, |_, cx| cx.notify());
                }
            }
            self.active_chat = active;
            cx.emit(HostEvent::SessionOpened);
            cx.notify();
        }
    }
}
impl Chat {
pub fn new(
        api: Api,
        workspace: WeakEntity<crate::ui::workspace::Workspace>,
        session_dir: PathBuf,
        prepared_stream: Option<async_channel::Receiver<crate::connection::PumpItem>>,
        extras: ComposerExtras,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) -> Self {
        let events = prepared_stream
            .unwrap_or_else(|| crate::connection::spawn_pump(api.clone(), session_dir.clone()));
        let initial = crate::connection::take_initial_events(&events);
        let mut chat = Self::base(
            Some(api),
            workspace,
            Session::new(session_dir),
            extras,
            window,
            cx,
        );
        chat._pump = Some(pump::start(events, cx));
        chat.apply_batch(initial, cx);
        chat.load_config(cx);
        chat
    }
pub fn apply(&mut self, item: PumpItem, cx: &mut Context<Self>) -> bool {
        let session = &mut self.session;
        match item {
            PumpItem::Connected => {
                // A reconnect baseline does not carry profile/config state.
                // Initial setup already starts its own config request.
                let reconnecting = session.link_error.is_some();
                self.context_requests.invalidate();
                session.stream_connected();
                if reconnecting {
                    self.load_config(cx);
                }
                cx.emit(ChatEvent::state_changed());
                true
            }
            PumpItem::Disconnected(error) => {
                session.stream_disconnected(error);
                cx.emit(ChatEvent::state_changed());
                true
            }
            PumpItem::Event(event) => self.apply_event(*event, cx),
        }
    }
}
impl Session{
pub fn stream_connected(&mut self) {
        self.cursor.begin_connection();
        self.pending_cursor.begin_connection();
        self.connected = true;
        self.link_error = None;
        self.stream_closed = false;
    }
pub fn stream_disconnected(&mut self, error: String) {
        self.feedback.clear_activity();
        self.connected = false;
        self.link_error = Some(error.into());
        self.stream_closed = false;
    }
}
pub fn core(
    slot: &Arc<Mutex<Option<CoreConnection>>>,
    options: &LaunchOptions,
) -> Result<(Api, Option<async_channel::Receiver<String>>)> {
    let mut slot = slot.lock().unwrap();
    if let Some(core) = slot.as_ref() {
        return Ok((core.api.clone(), None));
    }
    let (api, backend) = connection::connect(options)?;
    let exited = backend.as_ref().map(|guard| guard.exited.clone());
    *slot = Some(CoreConnection {
        api: api.clone(),
        backend,
    });
    Ok((api, exited))
}
