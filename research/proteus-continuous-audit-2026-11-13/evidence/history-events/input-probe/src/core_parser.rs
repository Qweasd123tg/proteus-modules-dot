use std::collections::HashMap;
use anyhow::{Result,anyhow,bail};
use serde::Deserialize;
use serde_json::Value;
use proteus_contracts::contracts::{UserInputAnswer,UserInputQuestion,UserInputQuestionOption,UserInputRequest};
#[derive(Debug, Deserialize)]
struct RequestUserInputArgs {
    #[serde(default)]
    questions: Vec<RequestUserInputQuestionArg>,
    #[serde(default)]
    title: Option<String>,
    #[serde(default)]
    id: Option<String>,
    #[serde(default)]
    header: Option<String>,
    #[serde(default)]
    question: Option<String>,
    #[serde(default, rename = "multiSelect")]
    multi_select: bool,
    #[serde(default)]
    options: Vec<RequestUserInputOptionArg>,
}

#[derive(Debug, Deserialize)]
struct RequestUserInputQuestionArg {
    #[serde(default)]
    id: Option<String>,
    header: String,
    question: String,
    #[serde(default, rename = "multiSelect")]
    multi_select: bool,
    options: Vec<RequestUserInputOptionArg>,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum RequestUserInputOptionArg {
    Object {
        label: String,
        #[serde(default)]
        description: Option<String>,
        #[serde(default)]
        preview: Option<String>,
    },
    Label(String),
}

fn parse_request(
    value: Value,
    request_id: String,
    cwd: std::path::PathBuf,
) -> Result<UserInputRequest> {
    let mut args: RequestUserInputArgs = serde_json::from_value(value)
        .map_err(|error| anyhow!("request_user_input: invalid args: {error}"))?;
    let questions = questions_from_args(&mut args)?;
    let mut request = UserInputRequest::new(request_id, cwd, questions);
    if let Some(title) = args.title.filter(|title| !title.trim().is_empty()) {
        request = request.with_title(title);
    }
    Ok(request)
}

#[cfg(test)]
fn parse_questions(value: Value) -> Result<Vec<UserInputQuestion>> {
    let mut args: RequestUserInputArgs = serde_json::from_value(value)
        .map_err(|error| anyhow!("request_user_input: invalid args: {error}"))?;
    questions_from_args(&mut args)
}

fn questions_from_args(args: &mut RequestUserInputArgs) -> Result<Vec<UserInputQuestion>> {
    if args.questions.is_empty() {
        if args.question.is_none() && args.header.is_none() && args.options.is_empty() {
            bail!("request_user_input requires questions or a single question");
        }
        args.questions.push(RequestUserInputQuestionArg {
            id: args.id.take(),
            header: args.header.take().unwrap_or_else(|| "Question".to_owned()),
            question: args.question.take().unwrap_or_default(),
            multi_select: args.multi_select,
            options: std::mem::take(&mut args.options),
        });
    }
    normalize_questions(std::mem::take(&mut args.questions))
}

fn normalize_questions(
    questions: Vec<RequestUserInputQuestionArg>,
) -> Result<Vec<UserInputQuestion>> {
    if questions.is_empty() {
        bail!("request_user_input requires at least one question");
    }
    if questions.len() > 3 {
        bail!("request_user_input supports at most three questions");
    }
    questions
        .into_iter()
        .map(|question| {
            if question.header.trim().is_empty() {
                bail!("request_user_input question header must be non-empty");
            }
            if question.question.trim().is_empty() {
                bail!("request_user_input question text must be non-empty");
            }
            if question.options.is_empty() {
                bail!("request_user_input requires non-empty options for every question");
            }
            if question.options.len() > 4 {
                bail!("request_user_input supports at most four options per question");
            }
            let multi_select = question.multi_select;
            let id = question
                .id
                .filter(|id| !id.trim().is_empty())
                .unwrap_or_else(|| question.question.clone());
            let options = question
                .options
                .into_iter()
                .map(|option| match option {
                    RequestUserInputOptionArg::Object {
                        label,
                        description,
                        preview,
                    } => {
                        let option =
                            UserInputQuestionOption::new(label, description.unwrap_or_default());
                        if let Some(preview) = preview.filter(|preview| !preview.trim().is_empty())
                        {
                            option.with_preview(preview)
                        } else {
                            option
                        }
                    }
                    RequestUserInputOptionArg::Label(label) => {
                        UserInputQuestionOption::new(label, "")
                    }
                })
                .collect();
            Ok(
                UserInputQuestion::new(id, question.header, question.question, options)
                    .with_multi_select(multi_select),
            )
        })
        .collect()
}

fn format_user_input_response(answers: &HashMap<String, UserInputAnswer>) -> String {
    if answers.is_empty() {
        return "User did not provide answers.".to_owned();
    }
    let mut entries = answers.iter().collect::<Vec<_>>();
    entries.sort_by_key(|(key, _)| *key);
    let summary = entries
        .into_iter()
        .map(|(question_id, answer)| {
            let answer = answer.answers.join(", ");
            format!("{question_id}: {answer}")
        })
        .collect::<Vec<_>>()
        .join("\n");
    format!("User answered:\n{summary}")
}

