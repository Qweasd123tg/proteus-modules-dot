use proteus_extension::Value;
use proteus_extension::ui::{Node, button, card, metric, row};

const MAX: u16 = 999;

#[derive(Default)]
pub struct Tally {
    rows: u16,
}

impl Tally {
    pub fn act(&mut self, action: &str) {
        match action {
            "add" if self.rows < MAX => self.rows += 1,
            "undo" => self.rows = self.rows.saturating_sub(1),
            "reset" => self.rows = 0,
            _ => {}
        }
    }

    pub fn view(&self) -> Value {
        card(
            Some("Счётчик рядов"),
            vec![
                metric("Готово рядов", self.rows),
                row(vec![
                    button("+1 ряд", "add").with("disabled", self.rows == MAX),
                    button("−1 ряд", "undo").with("disabled", self.rows == 0),
                    button("Сбросить", "reset").with("disabled", self.rows == 0),
                ]),
            ],
        )
    }
}
