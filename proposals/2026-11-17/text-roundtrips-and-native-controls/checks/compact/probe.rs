#![allow(dead_code)]
use serde_json::{json, Value};
mod domain { include!("core_types.rs"); }
use domain::{ConfigChoice,ConfigField,ConfigValueSchema};
include!("current.rs");
#[test]
fn existing_public_examples() {
    // Same JSON-field fixture and format/parse assertions as the upstream
    // mixed settings test; this checks the relevant slice, not that entire test.
    let limit=ConfigField::new("limit","Предел","",ConfigValueSchema::Json {}).with_default(100000);
    assert!(matches!(field_kind(&limit),FieldKind::Text(TextFormat::Value)));
    assert_eq!(parse_text(TextFormat::Value,"80%"),Ok(Some(json!("80%"))));
    assert_eq!(parse_text(TextFormat::Value,"100000"),Ok(Some(json!(100000))));
    assert_eq!(format_value(TextFormat::Value,&json!("80%")),"80%");
    assert_eq!(format_value(TextFormat::Value,&json!("5")),"\"5\"");
}
fn main() {
    use std::io::{self,BufRead};
    // Choose the control via the exact public construction and client type
    // dispatch; the supplied localized title/description are ordinary data.
    let schema=domain::ModuleConfigSchema{fields:vec![
       ConfigField::new("unit_label","Единица","Подпись значения",ConfigValueSchema::Json {}).with_default("°C")
    ]};
    let schema:domain::ModuleConfigSchema=serde_json::from_value(serde_json::to_value(schema).unwrap()).unwrap();
    let FieldKind::Text(fmt @ TextFormat::Value)=field_kind(&schema.fields[0]) else { panic!("wrong field kind") };
    for line in io::stdin().lock().lines(){let v:Value=serde_json::from_str(&line.unwrap()).unwrap();
      let shown=format_value(fmt,&v);
      let parsed=parse_text(fmt,&shown).unwrap();
      let manual=v.as_str().map(|s|parse_text(fmt,s).unwrap());
      println!("{}",json!({"original":v,"shown":shown,"absent":parsed.is_none(),"parsed":parsed,"manual":manual}));
    }
}
