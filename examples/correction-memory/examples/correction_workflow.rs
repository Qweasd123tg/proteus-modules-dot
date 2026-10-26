mod support;
fn main() -> anyhow::Result<()> {
    println!("{}", serde_json::to_string_pretty(&support::workflow()?)?);
    Ok(())
}
