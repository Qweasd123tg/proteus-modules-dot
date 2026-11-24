
impl RemoteSessionStore {
    pub(crate) fn test_revision(&self)->String {RemoteCacheSource{snapshot:self.snapshot.clone()}.revision().unwrap()}
    pub(crate) fn observed_headers_fixture(&self,revision:&str)->(Option<serde_json::Value>,Option<serde_json::Value>){
        fn normalize(st:&RemoteSessionStore,h:cache::Header)->serde_json::Value{
            let decoded=h.prefix.as_deref().map(|etag|cache::read_prefix(st,etag).expect("real persisted cache hash, packed prefix decode and validation"));
            let mut value=serde_json::to_value(h).unwrap();
            value["prefix"]=decoded.map_or(serde_json::Value::Null,|mut p|{
                // Keep hundreds of thousands of Number objects out of this read-back construction.
                // The exact ordered history still enters the independent test oracle whole.
                let messages=crate::canonical(&st.records);
                assert_eq!(p.history.len(),messages.len());
                for (expected,m) in p.history.iter().zip(messages){assert_eq!(*expected,crate::core::history_message_sha256(m).unwrap());}
                let versions=crate::identity_set_oracle(&st.records);
                assert_eq!(p.messages,versions.0);
                assert_eq!(p.parts,versions.1);
                assert_eq!(p.explicit_committed_parts,versions.1);
                let history=std::mem::take(&mut p.history);
                let mut cert=serde_json::to_value(&p).unwrap();
                cert["history"]=serde_json::Value::String(crate::sha(history.as_flattened()));
                for field in ["turns","exchanges","messages","parts","explicit_committed_parts","calls"]{
                    cert[field].as_array_mut().unwrap().sort_by_key(|x|x.to_string());
                }
                cert
            });
            value
        }
        let named=cache::header_at_revision(self,revision).map(|h|normalize(self,h));
        let latest=fixture_head(self).map(|h|normalize(self,h));
        (named,latest)
    }
}
fn fixture_head(st:&RemoteSessionStore)->Option<cache::Header>{
    let docs=st.docs.lock().unwrap();
    let v=docs.get(crate::HEAD)?;
    assert_eq!(v.etag,crate::storage_value_etag(&v.value).unwrap());
    Some(serde_json::from_value(v.value.clone()).unwrap())
}
