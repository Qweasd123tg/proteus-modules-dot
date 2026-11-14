#![allow(dead_code,private_interfaces)]
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
