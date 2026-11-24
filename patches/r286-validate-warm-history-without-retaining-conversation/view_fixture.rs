impl RemoteSessionStore{
 pub(crate) fn prepare_warm(&self,context_count:usize)->Result<()>{
    let (source,mut model)=self.project_sourced_read_model(None,crate::render_seed)?;
    if context_count>0{
      assert_eq!(model.conversation.model_context,[ModelContextObservation::HistoryCompacted]);
      if context_count>1{
       // The persisted fault fixture needs multiple logical context leaves.
       // Supply extra typed observations to the genuine writer, do not
       // construct raw stand-ins for an accepted context DTO.
       model.conversation.model_context=crate::expected_context(context_count);
       self.docs.lock().unwrap().clear();
       self.save_read_model(&source,&model);
      }
    }
    Ok(())
 }
 pub(crate) fn test_revision(&self)->String {RemoteCacheSource{snapshot:self.snapshot.clone()}.revision().unwrap()}
 pub(crate) fn warm_header(&self)->Value{
  let docs=self.docs.lock().unwrap();docs.get(crate::HEAD).unwrap().value.clone()
 }
 // The adapter's tested physical content: use genuine published section body.
 // For well-hashed corruption recalculate leaf and pack ETags and rewrite
 // the bound HEAD reference exactly as storage would; malformed DTO must still be rejected.
 pub(crate) fn damage(&self,section:&str,late:bool,how:&str)->(String,bool) {
  use base64::{Engine as _,engine::general_purpose::STANDARD};
  use miniz_oxide::{deflate::compress_to_vec,inflate::decompress_to_vec_with_limit};
  fn document(v:Value)->StorageMetadataDocument{
   StorageMetadataDocument{etag:storage_value_etag(&v).unwrap(),value:v}
  }
  let mut docs=self.docs.lock().unwrap();let mut head=docs.get(crate::HEAD).unwrap().value.clone();
  let sec=&mut head[section];let num=sec["pages"].as_array().unwrap().len();assert!(num>0);
  let i=if late{num-1}else{0};
  let pack=sec["packs"].as_array().and_then(|xs|xs.iter().enumerate().find(|(_,p)|{
   let first=p["first"].as_u64().unwrap() as usize;let count=p["count"].as_u64().unwrap() as usize;
   i>=first && i<first+count
  }).map(|(idx,p)|(idx,p.clone())));
  let leaf=sec["pages"][i]["hash"].as_str().unwrap().to_owned();
  let physical=pack.as_ref().map_or(leaf.as_str(),|(_,p)|p["hash"].as_str().unwrap());
  let key=format!("display-data-{physical}");
  let old=docs.get(&key).unwrap().value.clone();
  assert_eq!(storage_value_etag(&old).unwrap(),physical);
  if how=="missing"{docs.remove(&key);return(key,pack.is_some());}
  if how=="wrong-hash"{docs.insert(key.clone(),document(json!(["wrong key, otherwise typed fixture value"])));return(key,pack.is_some());}
  if matches!(how,"storage-wrong-kind"|"storage-failure"){return(key,pack.is_some());}
  if how=="packed-bytes" || how=="singleton-bytes"{
   assert_eq!(pack.is_some(),how=="packed-bytes");
   let old=sec["pages"][i]["bytes"].as_u64().unwrap();
   sec["pages"][i]["bytes"]=json!(if how=="packed-bytes"{old+1}else{(SESSION_STORAGE_MAX_CACHE_BYTES+1) as u64});
   docs.insert(crate::HEAD.into(),document(head));
   return(key,pack.is_some());
  }
  let mut physical_doc=old;
  let mut body=if let Some((_,p))=&pack{
   let off=i-p["first"].as_u64().unwrap() as usize;
   let frame=physical_doc["deflate_v1"][off].as_str().unwrap();
   if how=="deflate"{
    physical_doc["deflate_v1"][off]=json!("AAM="); // Well-keyed corrupt packed frame.
    let hdr=document(physical_doc);
    let idx=pack.as_ref().unwrap().0;
    sec["packs"][idx]["hash"]=json!(hdr.etag);
    let k=format!("display-data-{}",hdr.etag);
    docs.insert(k.clone(),hdr);docs.insert(crate::HEAD.into(),document(head));
    return(k,true)
   }
   let compressed=STANDARD.decode(frame).unwrap();
   let bytes=decompress_to_vec_with_limit(&compressed,262144).unwrap();
   assert_eq!(sec["pages"][i]["bytes"].as_u64(),Some(bytes.len() as u64));
   serde_json::from_slice::<Value>(&bytes).unwrap()
  } else {physical_doc.clone()};
  assert_eq!(storage_value_etag(&body).unwrap(),leaf);
  match how{
   "type"=>{let ix=body.as_array().unwrap().len()/2;body[ix]=Value::Null;}
   "count"=>{assert!(body.as_array_mut().unwrap().pop().is_some());}
   _=>unreachable!()
  }
  let data=crate::bytes(&body);let leaf=storage_value_etag(&body).unwrap();
  sec["pages"][i]["hash"]=json!(leaf);sec["pages"][i]["bytes"]=json!(data.len());
  let value=if let Some((idx,p))=&pack{
   let off=i-p["first"].as_u64().unwrap() as usize;
   physical_doc["deflate_v1"][off]=json!(STANDARD.encode(compress_to_vec(&data,1)));
   sec["packs"][*idx]["hash"]=json!(storage_value_etag(&physical_doc).unwrap());
   physical_doc
  }else{body};
  let doc=document(value);let k=format!("display-data-{}",doc.etag);docs.insert(k.clone(),doc);docs.insert(crate::HEAD.into(),document(head));
  (k,pack.is_some())
 }
 pub(crate) fn alter_head(&self,how:&str){
  let mut docs=self.docs.lock().unwrap();let mut h=docs.get(crate::HEAD).unwrap().value.clone();
  match how{"invalid-head"=>h["format"]=json!(999),"false-head"=>h["summary"]["workspace_path"]=json!("/different"),"count-head"=>{
    assert_ne!(h["transcript"]["rows"],json!(0));
    h["summary"]["message_count"]=json!(h["summary"]["message_count"].as_u64().unwrap()+1);
    h["conversation"]=json!({"rows":0,"pages":[]});
  },_=>unreachable!()}
  let etag=storage_value_etag(&h).unwrap();docs.insert(crate::HEAD.into(),StorageMetadataDocument{etag,value:h});
 }
 pub(crate) fn cache_proof(&self)->(Value,String,usize){
  let docs=self.docs.lock().unwrap();
  let mut pages=BTreeMap::new();
  for (k,doc) in docs.iter(){
   if k.starts_with("display-data-"){
    // Deliberate wrong-hash fault may leave an obsolete object after fallback.
    pages.insert(k.clone(),(doc.etag.clone(),crate::sha(&crate::bytes(&doc.value))));
   }
  }
  let header=docs.get(crate::HEAD).map(|doc|{let mut v=doc.value.clone();v["prefix"]=Value::Null;v}).unwrap_or(Value::Null);
  (header,crate::sha(&crate::bytes(&pages)),pages.len())
 }
}
