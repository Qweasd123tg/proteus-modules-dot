mod header {include!("frame-source.rs");}
include!("table-source.rs");
fn main(){
    let names=["AB", "Пр", "東京", "é", "e\u{301}"];
    let values:Vec<_>=names.iter().map(|street|format!("cwd: /work/{street}")).collect();
    println!("{}",header::small_block("Proteus",&values));
    println!("--tables--");
    // Ordinary names rather than a claim about which package ID strings are accepted.
    let table_rows=names.map(|name| [name.to_owned(),"target".to_owned()]);
    println!("{}",render_table(["name","slot"],&table_rows));
}
