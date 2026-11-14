from pathlib import Path
import hashlib
out=Path('/workspace/shared/history-events-evidence/input-probe/src')
core_path=Path('/workspace/shared/history-events-audit/crates/proteus-core/src/tools/request_user_input.rs')
ui_path=Path('/workspace/shared/state-install-trace/src/ui/chat/user_input.rs')
c=core_path.read_text(); u=ui_path.read_text()
ctypes=c[c.index('#[derive(Debug, Deserialize)]'):c.index('#[async_trait]')]
funcs=c[c.index('fn parse_request('):c.index('#[cfg(test)]\nmod tests')]
(out/'core_parser.rs').write_text('use std::collections::HashMap;\nuse anyhow::{Result,anyhow,bail};\nuse serde::Deserialize;\nuse serde_json::Value;\nuse proteus_contracts::contracts::{UserInputAnswer,UserInputQuestion,UserInputQuestionOption,UserInputRequest};\n'+ctypes+funcs)
# Retain exact production fields and pure-state methods. Only GPUI creation /
# mutation methods are omitted; Entity::read stub exposes pre-set test text.
body=u[u.index('#[derive(Default)]'):]
for marker in ['    pub fn clear(', '    pub fn text_input(']:
    start=body.index(marker); b=body.index('{',start); depth=1; end=b+1
    while depth:
        depth += (body[end]=='{')-(body[end]=='}'); end+=1
    body=body[:start]+body[end:]
stubs='''use std::collections::HashMap;
use proteus_contracts::app_protocol::AppPendingRequests;
use proteus_contracts::contracts::{UserInputAnswer,UserInputRequest,UserInputResponse};
struct App;
struct InputState{ value:String }
impl InputState{fn value(&self)->&str{&self.value}}
struct Entity<T>(T);
impl<T> Entity<T>{fn read<'a>(&'a self,_:&App)->&'a T{&self.0}}
struct Subscription;
'''
(out/'ui_state.rs').write_text(stubs+body)
(out/'lib.rs').write_text('''#![allow(dead_code,private_interfaces)]
mod parser { include!("core_parser.rs");
pub fn parse(value: serde_json::Value) -> UserInputRequest {parse_request(value, "unique-call".into(), "/synthetic".into()).unwrap()}
}
mod state { include!("ui_state.rs");
#[cfg(test)] mod audit {
use super::*;
use serde_json::json;
#[test]
fn duplicate_question_ids_share_answers_and_drop_one_question() {
 let request=crate::parser::parse(json!({"questions":[
  {"id":"choice","header":"Language","question":"Which language?","options":["Rust","Python"]},
  {"id":"choice","header":"Database","question":"Which database?","options":["SQLite","Postgres"]}
 ]}));
 assert_eq!(request.questions.len(),2);
 let mut draft=UserInputDrafts::default();let cx=App;
 draft.toggle(&request.request_id,&request.questions[0].id,"Rust",false);
 assert!(draft.is_answered(&request.request_id,&request.questions[1].id,&cx),"second question already marked answered despite no selection from its options");
 draft.toggle(&request.request_id,&request.questions[1].id,"SQLite",false);
 let response=draft.response(&request,&cx);
 assert_eq!(response.answers.len(),1);
 assert_eq!(response.answers["choice"].answers,vec!["SQLite"]);
 println!("AUDIT: questions={} second_pretends_answered=true answers={}",request.questions.len(),serde_json::to_string(&response).unwrap());
}
#[test]
fn distinct_ids_preserve_two_independent_answers_control() {
 let request=crate::parser::parse(json!({"questions":[
  {"id":"language","header":"Language","question":"Which language?","options":["Rust","Python"]},
  {"id":"database","header":"Database","question":"Which database?","options":["SQLite","Postgres"]}
 ]}));
 let mut draft=UserInputDrafts::default();let cx=App;
 draft.toggle(&request.request_id,"language","Rust",false);
 assert!(!draft.is_answered(&request.request_id,"database",&cx));
 draft.toggle(&request.request_id,"database","SQLite",false);
 let response=draft.response(&request,&cx);
 assert_eq!(response.answers.len(),2);
 assert_eq!(response.answers["language"].answers,vec!["Rust"]);
 assert_eq!(response.answers["database"].answers,vec!["SQLite"]);
}
}
}
''')
Path('/workspace/shared/history-events-evidence/input-extraction.txt').write_text('Core parser + structs are exact source slices, unchanged. Desktop state struct and all pure-state methods are exact source slices; only clear/text_input (GPUI mutation/creation) omitted. Entity.read and InputState.value stubbed to expose a preset string, no rendering or transport claimed. Tests use option-selection paths.\n'+ '\n'.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()} {p}' for p in [core_path,ui_path])+'\n')
