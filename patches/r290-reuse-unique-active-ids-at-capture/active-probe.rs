// Proof-only adapter; invokes exact checks above without fabricating their work.
impl JournalValidationState {
    pub(super) fn observe_captured_active_ids(&mut self,index:usize,candidate:bool)->Result<()>{
        let prior=self.active_ids.as_ref().map(Arc::as_ptr);
        let present=prior.is_some();
        let unique=self.active_ids.as_ref().is_some_and(|x|Arc::strong_count(x)==1 && Arc::weak_count(x)==0);
        proof_bridge::active_begin(index,self.history.len(),unique,present);
        let result=if candidate {self.check_captured_active_ids(index)}else{self.check_active_ids(None)};
        let fast=proof_bridge::active_finish(index,result.is_ok());
        if fast {assert!(result.is_ok() && unique && present);assert_eq!(prior,self.active_ids.as_ref().map(Arc::as_ptr));}
        if result.is_err(){assert!(self.active_ids.is_none());}
        result
    }

    pub(super) fn proof_memberships(&self)->Option<(Vec<MessageId>,Vec<PartId>)>{
        self.active_ids.as_ref().map(|a|{
            let mut m=a.messages.iter().copied().collect::<Vec<_>>();
            let mut p=a.parts.iter().copied().collect::<Vec<_>>();
            m.sort_unstable();p.sort_unstable();
            (m,p)
        })
    }
}
