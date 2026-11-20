use proteus_contracts::{app_protocol::{AppTranscriptMessage,AppTranscriptTool,AppTranscriptSubagent},domain::{ImageRef,MessageId},model_standard::MessagePhase};
use std::mem::{size_of,align_of};
#[allow(dead_code)] struct SparseLayout {
message_id: Option<MessageId>, timestamp_ms: Option<i64>, phase: Option<MessagePhase>, role: String, text: String, images: Vec<ImageRef>, tool: Option<Box<AppTranscriptTool>>, subagent: Option<Box<AppTranscriptSubagent>>, streaming: bool,
}
fn main(){
println!("actual row {} align {} sparse candidate {} align {} tool slot {} subagent slot {} box_slot {}",size_of::<AppTranscriptMessage>(),align_of::<AppTranscriptMessage>(),size_of::<SparseLayout>(),align_of::<SparseLayout>(),size_of::<Option<AppTranscriptTool>>(),size_of::<Option<AppTranscriptSubagent>>(),size_of::<Option<Box<AppTranscriptTool>>>());
}
