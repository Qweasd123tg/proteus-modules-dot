impl RemoteSessionStore{
 pub(crate) fn test_revision(&self)->String {RemoteCacheSource{snapshot:self.snapshot.clone()}.revision().unwrap()}
 pub(crate) fn cache_proof(&self)->(Value,String,usize){
  let docs=self.docs.lock().unwrap();
  let mut cert=BTreeMap::new();
  for (k,doc) in docs.iter(){
   assert_eq!(storage_value_etag(&doc.value).unwrap(),doc.etag);
   if k.starts_with("display-data-"){
    assert_eq!(k.strip_prefix("display-data-"),Some(doc.etag.as_str()));
    cert.insert(k.clone(),crate::sha(&crate::bytes(&doc.value)));
   }
  }
  let header=docs.get(crate::HEAD).map(|doc|{let mut v=doc.value.clone();v["prefix"]=Value::Null;v}).unwrap_or(Value::Null);
  (header,crate::sha(&crate::bytes(&cert)),cert.len())
 }
}
