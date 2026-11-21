use super::super::execution::ExecutionAdmissionSnapshot;

impl AgentRuntime {
    pub async fn r57_stock_start_session(&self) -> Result<()> {
        self.r57_stock_ensure_session_started().await
    }

    async fn r57_stock_ensure_session_started(&self) -> Result<()> {
        let snapshot = self.capture_execution_snapshot().await;
        self.r57_stock_ensure_session_started_with_snapshot(&snapshot).await
    }

    async fn r57_stock_ensure_session_started_with_snapshot(
        &self,
        snapshot: &ExecutionAdmissionSnapshot,
    ) -> Result<()> {
        let mut started = self.session.session_started.lock().await;
        if *started {
            return Ok(());
        }

        self.services
            .events
            .emit(
                EventContext::new(self.session.session_id, self.session.thread_id, None),
                Event::SessionStarted {
                    session_id: self.session.session_id,
                    cwd: self.services.cwd.clone(),
                    model: snapshot.model_ref.clone(),
                    session_dir: self.session_dir().map(|path| path.to_path_buf()),
                },
            )
            .await?;
        *started = true;
        Ok(())
    }

}
