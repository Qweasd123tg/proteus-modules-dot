//! Pure advisory planning. Supplied statuses are assertions, never execution evidence.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

pub const MAX_NODES: usize = 256;
pub const MAX_EDGES: usize = 4096;
pub const MAX_ID_BYTES: usize = 64;
pub const MAX_OUTPUT_BYTES: usize = 64_000;

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Pending,
    Running,
    Succeeded,
    Failed,
    Canceled,
}

impl Status {
    fn terminal(self) -> bool {
        matches!(self, Self::Succeeded | Self::Failed | Self::Canceled)
    }

    fn unsuccessful(self) -> bool {
        matches!(self, Self::Failed | Self::Canceled)
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FailurePolicy {
    /// A failure anywhere suppresses every new recommendation; running work is untouched.
    FailFast,
    /// A pending node can follow any terminal dependencies, including unsuccessful ones.
    AllSettled,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub id: String,
    pub dependencies: Vec<String>,
    pub status: Status,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Input {
    pub nodes: Vec<Node>,
    pub failure_policy: FailurePolicy,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct Blocked {
    pub id: String,
    pub reason: BlockReason,
    /// Immediate dependencies that are not terminal in the supplied snapshot.
    pub waiting_for: Vec<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum BlockReason {
    FailurePolicy,
    WaitingDependencies,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct Output {
    pub advisory_only: bool,
    pub status_source: &'static str,
    pub failure_policy: FailurePolicy,
    pub admission_halted: bool,
    pub ready: Vec<String>,
    pub blocked: Vec<Blocked>,
    pub running: Vec<String>,
    pub terminal: Vec<String>,
    pub unsuccessful: Vec<String>,
    /// Transitive failed/canceled ancestors for pending nodes; may include ready nodes.
    pub failed_dependencies: BTreeMap<String, Vec<String>>,
    pub topological_order: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AnalysisError {
    Invalid(String),
    Canceled,
    CancellationCheck(String),
}

impl std::fmt::Display for AnalysisError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Invalid(message) => write!(formatter, "invalid plan: {message}"),
            Self::Canceled => write!(formatter, "planning canceled"),
            Self::CancellationCheck(message) => {
                write!(formatter, "cancellation check failed: {message}")
            }
        }
    }
}

impl std::error::Error for AnalysisError {}

/// Return complete JSON or an explicit error, never silently cut a graph result.
pub fn encode_output(output: &Output) -> Result<String, AnalysisError> {
    let text = serde_json::to_string(output).map_err(|error| invalid(error.to_string()))?;
    if text.len() > MAX_OUTPUT_BYTES {
        return Err(invalid(format!(
            "analysis exceeds {MAX_OUTPUT_BYTES} output bytes; use a smaller graph or shorter IDs"
        )));
    }
    Ok(text)
}

fn invalid(message: impl Into<String>) -> AnalysisError {
    AnalysisError::Invalid(message.into())
}

fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= MAX_ID_BYTES
        && id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

/// Analyze a bounded DAG. The callback is polled before work, at each graph node,
/// and before returning. A failed callback is not treated as permission to continue.
pub fn analyze(
    input: &Input,
    mut canceled: impl FnMut() -> Result<bool, String>,
) -> Result<Output, AnalysisError> {
    let mut check = || match canceled() {
        Ok(false) => Ok(()),
        Ok(true) => Err(AnalysisError::Canceled),
        Err(message) => Err(AnalysisError::CancellationCheck(message)),
    };
    check()?;
    if input.nodes.len() > MAX_NODES {
        return Err(invalid(format!("at most {MAX_NODES} nodes are allowed")));
    }

    let mut nodes = BTreeMap::new();
    let mut edges = 0usize;
    for node in &input.nodes {
        check()?;
        if !valid_id(&node.id) {
            return Err(invalid(
                "IDs must be 1..64 ASCII letters, digits, '.', '_' or '-'",
            ));
        }
        if nodes.insert(node.id.clone(), node).is_some() {
            return Err(invalid(format!("duplicate node ID {}", node.id)));
        }
        if node.dependencies.len() > MAX_NODES {
            return Err(invalid(format!("too many dependencies for {}", node.id)));
        }
        edges = edges
            .checked_add(node.dependencies.len())
            .ok_or_else(|| invalid("edge count overflow"))?;
        if edges > MAX_EDGES {
            return Err(invalid(format!("at most {MAX_EDGES} edges are allowed")));
        }
    }

    let mut indegree = BTreeMap::new();
    let mut children: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (id, node) in &nodes {
        check()?;
        let mut seen = BTreeSet::new();
        for dependency in &node.dependencies {
            if !valid_id(dependency) {
                return Err(invalid(
                    "dependency IDs must be 1..64 bounded ASCII characters",
                ));
            }
            if dependency == id {
                return Err(invalid(format!("self dependency on {id}")));
            }
            if !nodes.contains_key(dependency) {
                return Err(invalid(format!(
                    "node {id} references missing dependency {dependency}"
                )));
            }
            if !seen.insert(dependency) {
                return Err(invalid(format!(
                    "node {id} repeats dependency {dependency}"
                )));
            }
            children
                .entry(dependency.clone())
                .or_default()
                .push(id.clone());
        }
        indegree.insert(id.clone(), seen.len());
    }
    let mut frontier: BTreeSet<String> = indegree
        .iter()
        .filter(|(_, count)| **count == 0)
        .map(|(id, _)| id.clone())
        .collect();
    let mut order = Vec::with_capacity(nodes.len());
    while let Some(id) = frontier.pop_first() {
        check()?;
        if let Some(dependents) = children.get(&id) {
            for child in dependents {
                let count = indegree
                    .get_mut(child)
                    .expect("all children were validated");
                *count -= 1;
                if *count == 0 {
                    frontier.insert(child.clone());
                }
            }
        }
        order.push(id);
    }
    if order.len() != nodes.len() {
        return Err(invalid("dependency graph contains a cycle"));
    }

    // Bounded transitive annotations: <= MAX_NODES^2 IDs retained, no recursion.
    let mut failure_ancestors: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for id in &order {
        check()?;
        let mut failures = BTreeSet::new();
        for dependency in &nodes[id].dependencies {
            if nodes[dependency].status.unsuccessful() {
                failures.insert(dependency.clone());
            }
            failures.extend(failure_ancestors[dependency].iter().cloned());
        }
        failure_ancestors.insert(id.clone(), failures);
    }

    let unsuccessful: Vec<String> = nodes
        .iter()
        .filter(|(_, node)| node.status.unsuccessful())
        .map(|(id, _)| id.clone())
        .collect();
    let halted = input.failure_policy == FailurePolicy::FailFast && !unsuccessful.is_empty();
    let mut output = Output {
        advisory_only: true,
        status_source: "caller_supplied_unverified",
        failure_policy: input.failure_policy,
        admission_halted: halted,
        ready: Vec::new(),
        blocked: Vec::new(),
        running: Vec::new(),
        terminal: Vec::new(),
        unsuccessful,
        failed_dependencies: BTreeMap::new(),
        topological_order: order,
    };
    for (id, node) in &nodes {
        check()?;
        match node.status {
            Status::Running => output.running.push(id.clone()),
            Status::Succeeded | Status::Failed | Status::Canceled => {
                output.terminal.push(id.clone())
            }
            Status::Pending => {
                let mut waiting_for: Vec<String> = node
                    .dependencies
                    .iter()
                    .filter(|dependency| !nodes[*dependency].status.terminal())
                    .cloned()
                    .collect();
                waiting_for.sort();
                if !failure_ancestors[id].is_empty() {
                    output
                        .failed_dependencies
                        .insert(id.clone(), failure_ancestors[id].iter().cloned().collect());
                }
                if halted || !waiting_for.is_empty() {
                    output.blocked.push(Blocked {
                        id: id.clone(),
                        reason: if halted {
                            BlockReason::FailurePolicy
                        } else {
                            BlockReason::WaitingDependencies
                        },
                        waiting_for,
                    });
                } else {
                    output.ready.push(id.clone());
                }
            }
        }
    }
    check()?;
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn node(id: &str, dependencies: &[&str], status: Status) -> Node {
        Node {
            id: id.into(),
            dependencies: dependencies.iter().map(|value| (*value).into()).collect(),
            status,
        }
    }

    fn run(nodes: Vec<Node>, failure_policy: FailurePolicy) -> Result<Output, AnalysisError> {
        analyze(
            &Input {
                nodes,
                failure_policy,
            },
            || Ok(false),
        )
    }

    #[test]
    fn readiness_and_output_are_independent_of_input_order() {
        let nodes = vec![
            node("c", &["b", "a"], Status::Pending),
            node("b", &[], Status::Succeeded),
            node("a", &[], Status::Pending),
        ];
        let first = run(nodes.clone(), FailurePolicy::AllSettled).unwrap();
        let mut reversed = nodes;
        reversed.reverse();
        reversed
            .iter_mut()
            .for_each(|node| node.dependencies.reverse());
        assert_eq!(first, run(reversed, FailurePolicy::AllSettled).unwrap());
        assert_eq!(first.ready, ["a"]);
        assert_eq!(first.blocked[0].waiting_for, ["a"]);
        assert_eq!(first.topological_order, ["a", "b", "c"]);
        assert!(first.advisory_only);
        assert_eq!(first.status_source, "caller_supplied_unverified");
    }

    #[test]
    fn fail_fast_is_global_and_does_not_cancel_running_nodes() {
        let result = run(
            vec![
                node("bad", &[], Status::Failed),
                node("independent", &[], Status::Pending),
                node("active", &[], Status::Running),
            ],
            FailurePolicy::FailFast,
        )
        .unwrap();
        assert!(result.admission_halted && result.ready.is_empty());
        assert_eq!(result.running, ["active"]);
        assert_eq!(result.blocked[0].reason, BlockReason::FailurePolicy);
    }

    #[test]
    fn all_settled_releases_unsuccessful_dependencies_and_reports_transitive_failures() {
        let result = run(
            vec![
                node("bad", &[], Status::Canceled),
                node("middle", &["bad"], Status::Succeeded),
                node("next", &["middle"], Status::Pending),
            ],
            FailurePolicy::AllSettled,
        )
        .unwrap();
        assert_eq!(result.ready, ["next"]);
        assert_eq!(result.failed_dependencies["next"], ["bad"]);
        assert!(!result.admission_halted);
    }

    #[test]
    fn rejects_duplicates_dangling_refs_self_loops_and_cycles() {
        for nodes in [
            vec![
                node("a", &[], Status::Pending),
                node("a", &[], Status::Pending),
            ],
            vec![node("a", &["missing"], Status::Pending)],
            vec![node("a", &["a"], Status::Pending)],
            vec![
                node("a", &["b"], Status::Pending),
                node("b", &["a"], Status::Pending),
            ],
            vec![
                node("a", &[], Status::Pending),
                node("b", &["a", "a"], Status::Pending),
            ],
        ] {
            assert!(matches!(
                run(nodes, FailurePolicy::AllSettled),
                Err(AnalysisError::Invalid(_))
            ));
        }
    }

    #[test]
    fn validates_terminal_subgraphs_too() {
        assert!(
            run(
                vec![
                    node("a", &["b"], Status::Succeeded),
                    node("b", &["a"], Status::Succeeded)
                ],
                FailurePolicy::FailFast
            )
            .is_err()
        );
    }

    #[test]
    fn empty_and_maximum_chain_are_valid() {
        assert!(
            run(vec![], FailurePolicy::FailFast)
                .unwrap()
                .ready
                .is_empty()
        );
        let nodes = (0..MAX_NODES)
            .map(|index| Node {
                id: format!("n{index:03}"),
                dependencies: if index == 0 {
                    vec![]
                } else {
                    vec![format!("n{:03}", index - 1)]
                },
                status: Status::Pending,
            })
            .collect();
        let result = run(nodes, FailurePolicy::AllSettled).unwrap();
        assert_eq!(result.ready, ["n000"]);
        assert_eq!(result.topological_order.len(), MAX_NODES);
    }

    #[test]
    fn rejects_node_edge_and_string_limits() {
        assert!(
            run(
                (0..=MAX_NODES)
                    .map(|index| node(&format!("n{index}"), &[], Status::Pending))
                    .collect(),
                FailurePolicy::AllSettled
            )
            .is_err()
        );
        for id in [
            "".to_owned(),
            "x".repeat(MAX_ID_BYTES + 1),
            "не-ascii".into(),
            "../x".into(),
        ] {
            assert!(
                run(
                    vec![node(&id, &[], Status::Pending)],
                    FailurePolicy::AllSettled
                )
                .is_err()
            );
        }
        assert!(
            run(
                vec![node(&"x".repeat(MAX_ID_BYTES), &[], Status::Pending)],
                FailurePolicy::AllSettled
            )
            .is_ok()
        );
        let nodes = (0..100)
            .map(|index| Node {
                id: format!("n{index}"),
                dependencies: (0..index).map(|parent| format!("n{parent}")).collect(),
                status: Status::Pending,
            })
            .collect();
        assert!(
            run(nodes, FailurePolicy::AllSettled)
                .unwrap_err()
                .to_string()
                .contains("4096")
        );
    }

    #[test]
    fn cancellation_is_polled_during_work_and_failure_is_closed() {
        let input = Input {
            nodes: vec![node("a", &[], Status::Pending)],
            failure_policy: FailurePolicy::FailFast,
        };
        assert_eq!(analyze(&input, || Ok(true)), Err(AnalysisError::Canceled));
        let mut polls = 0;
        assert_eq!(
            analyze(&input, || {
                polls += 1;
                Ok(polls == 4)
            }),
            Err(AnalysisError::Canceled)
        );
        assert!(matches!(
            analyze(&input, || Err("host unavailable".into())),
            Err(AnalysisError::CancellationCheck(_))
        ));
    }

    #[test]
    fn rejects_unknown_fields_and_statuses() {
        for value in [
            serde_json::json!({"nodes": [], "failure_policy": "all_settled", "execute": true}),
            serde_json::json!({"nodes": [{"id": "a", "dependencies": [], "status": "verified"}], "failure_policy": "all_settled"}),
            serde_json::json!({"nodes": [{"id": "a", "dependencies": [], "status": "pending", "command": "run"}], "failure_policy": "all_settled"}),
        ] {
            assert!(serde_json::from_value::<Input>(value).is_err());
        }
    }

    #[test]
    fn oversized_results_fail_explicitly_instead_of_truncating_json() {
        let mut result = run(vec![], FailurePolicy::AllSettled).unwrap();
        assert!(
            serde_json::from_str::<serde_json::Value>(&encode_output(&result).unwrap()).is_ok()
        );
        result.ready = vec!["x".repeat(MAX_OUTPUT_BYTES)];
        assert!(encode_output(&result).is_err());
    }

    #[test]
    fn valid_graph_can_exceed_output_budget_without_partial_answer() {
        let id = |kind: char, index: usize| format!("{kind}{index:02}{}", "x".repeat(61));
        let mut nodes: Vec<Node> = (0..32)
            .map(|index| Node {
                id: id('f', index),
                dependencies: if index == 0 {
                    vec![]
                } else {
                    vec![id('f', index - 1)]
                },
                status: Status::Failed,
            })
            .collect();
        nodes.extend((0..32).map(|index| Node {
            id: id('p', index),
            dependencies: vec![id('f', 31)],
            status: Status::Pending,
        }));
        assert_eq!(nodes.len(), 64);
        assert_eq!(
            nodes
                .iter()
                .map(|node| node.dependencies.len())
                .sum::<usize>(),
            63
        );
        assert!(nodes.iter().all(|node| node.id.len() == MAX_ID_BYTES));
        let result = run(nodes, FailurePolicy::AllSettled).unwrap();
        assert_eq!(result.ready.len(), 32);
        assert!(
            result
                .failed_dependencies
                .values()
                .all(|ancestors| ancestors.len() == 32)
        );
        assert!(serde_json::to_string(&result).unwrap().len() > MAX_OUTPUT_BYTES);
        assert!(
            matches!(encode_output(&result), Err(AnalysisError::Invalid(message))
            if message.contains("64000 output bytes"))
        );
    }
}
