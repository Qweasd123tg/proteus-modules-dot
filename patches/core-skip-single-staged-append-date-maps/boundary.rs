// Strict replay semantics live at the validated-history boundary of this slice.
// Preserve the real open/scan/file stage path for the fixture's typed record stream.
fn validate(store:RemoteSessionStore,_previous:Option<()>,mut display:Option<DisplayRecordWriter>)->Result<(Self,bool)>{
   let mut source=RemoteJournalSnapshot::open(store)?;
   let mut next=1;
   source.scan(|record|{
       anyhow::ensure!(record.session_seq==next,"fixture replay sequence");
       next+=1;
       if let Some(display)=&mut display && is_display_kind(record.entry.kind()) {display.push(&record)}
       Ok(())
   })?;
   source.display_records=display.and_then(DisplayRecordWriter::finish);
   Ok((Self{source,resume:ResumeState,prefix_history_fingerprints:None},false))
}
