//! Pure, replaceable lexical ranking over already-discovered skill facts.
//!
//! No I/O, parsers, execution, permissions, clock, process-global state, or SDK
//! dependency. All caller-provided identities/freshness assertions are data, not
//! capabilities. Search requires a CURRENT host-filtered candidate set every time;
//! a hit never authorizes reading a document or running its contents.

#![forbid(unsafe_code)]

use std::{collections::BTreeMap, fmt};

pub const HARD_MAX_SKILLS: usize = 128;
pub const HARD_MAX_INPUT_BYTES: usize = 2_097_152;
pub const HARD_MAX_INPUT_BODY_BYTES: usize = 131_072;
pub const HARD_MAX_METADATA_BYTES: usize = 524_288;
pub const HARD_MAX_BODY_PREFIX_BYTES: usize = 16_384;
pub const HARD_MAX_BODY_TOTAL_BYTES: usize = 262_144;
pub const HARD_MAX_TERMS: usize = 32_768;
pub const HARD_MAX_TERM_BYTES: usize = 524_288;
pub const HARD_MAX_TERMS_PER_SKILL: usize = 2_048;
pub const MAX_ID_BYTES: usize = 128;
pub const MAX_SOURCE_BYTES: usize = 128;
pub const MAX_NAME_BYTES: usize = 64;
pub const MAX_DESCRIPTION_BYTES: usize = 4_096;
pub const MAX_TOKEN_BYTES: usize = 64;
pub const MAX_QUERY_BYTES: usize = 1_024;
pub const MAX_QUERY_TERMS: usize = 32;
pub const MAX_RESULTS: usize = 32;

const NAME: u8 = 1;
const DESCRIPTION: u8 = 2;
const BODY: u8 = 4;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Limits {
    pub max_skills: usize,
    pub max_input_bytes: usize,
    pub max_metadata_bytes: usize,
    pub max_body_skills: usize,
    pub max_body_prefix_bytes: usize,
    pub max_body_total_bytes: usize,
    pub max_terms: usize,
    pub max_term_bytes: usize,
    pub max_terms_per_skill: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            max_skills: HARD_MAX_SKILLS,
            max_input_bytes: HARD_MAX_INPUT_BYTES,
            max_metadata_bytes: HARD_MAX_METADATA_BYTES,
            max_body_skills: 64,
            max_body_prefix_bytes: HARD_MAX_BODY_PREFIX_BYTES,
            max_body_total_bytes: HARD_MAX_BODY_TOTAL_BYTES,
            max_terms: 16_384,
            max_term_bytes: 262_144,
            max_terms_per_skill: 1_024,
        }
    }
}

impl Limits {
    fn validate(self) -> Result<(), Error> {
        if self.max_skills == 0 || self.max_skills > HARD_MAX_SKILLS
            || self.max_input_bytes == 0 || self.max_input_bytes > HARD_MAX_INPUT_BYTES
            || self.max_metadata_bytes == 0 || self.max_metadata_bytes > HARD_MAX_METADATA_BYTES
            || self.max_body_skills > self.max_skills
            || self.max_body_prefix_bytes > HARD_MAX_BODY_PREFIX_BYTES
            || self.max_body_total_bytes > HARD_MAX_BODY_TOTAL_BYTES
            || self.max_terms == 0 || self.max_terms > HARD_MAX_TERMS
            || self.max_term_bytes == 0 || self.max_term_bytes > HARD_MAX_TERM_BYTES
            || self.max_terms_per_skill == 0
            || self.max_terms_per_skill > HARD_MAX_TERMS_PER_SKILL
        {
            return Err(Error::InvalidLimits);
        }
        Ok(())
    }
}

/// Host-owned scope identity, NOT a hash, permission token, or freshness proof.
/// Use a new binding_epoch when a process/export/config/root binding is replaced.
/// catalog_revision must change when ANY indexed fact changes, including bodies.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SnapshotKey {
    pub binding_epoch: u128,
    pub catalog_revision: u64,
}

/// Already-authorized, already-read UTF-8 body or prefix. No reading occurs here.
/// `complete=false` suppresses the final unterminated token to avoid false prefix
/// matches. The digest below must describe the FULL SKILL.md, not this prefix.
#[derive(Clone, Copy, Debug)]
pub struct BodyExcerpt<'a> {
    pub text: &'a str,
    pub complete: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct SkillFacts<'a> {
    pub id: &'a str,
    pub source_id: &'a str,
    pub sha256: [u8; 32],
    pub name: &'a str,
    pub description: &'a str,
    pub body: Option<BodyExcerpt<'a>>,
}

/// Supplied anew by the trusted adapter AFTER applying this invocation's config
/// and runtime disabled settings, source/read policy and model-invocation rules.
/// Constructing this struct does not perform or prove those checks.
#[derive(Clone, Copy, Debug)]
pub struct CurrentSkill<'a> {
    pub id: &'a str,
    pub source_id: &'a str,
    pub sha256: [u8; 32],
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct DocumentCoverage {
    /// Metadata terms longer than MAX_TOKEN_BYTES are not prefix-indexed.
    pub metadata_long_tokens_omitted: usize,
    pub body_supplied: bool,
    pub body_indexed: bool,
    pub body_prefix_bytes: usize,
    /// True for caller prefixes, byte/count budgets, token limits, or long words.
    pub body_partial: bool,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct IndexStatistics {
    pub skills: usize,
    pub validated_input_bytes: usize,
    pub retained_identity_bytes: usize,
    pub retained_terms: usize,
    pub retained_term_bytes: usize,
    pub body_prefix_bytes: usize,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct SearchCoverage {
    /// Counts only CURRENT candidates, not excluded/disabled index entries.
    pub eligible_skills: usize,
    pub metadata_partial_skills: usize,
    pub body_indexed_skills: usize,
    pub metadata_only_skills: usize,
    pub body_partial_skills: usize,
    pub body_budget_skipped_skills: usize,
    pub matched_skills: usize,
    pub returned_skills: usize,
}

/// Lexicographic score: exact name first, then distinct matched terms, then weight.
/// Repetition does not boost rank; strongest field per term wins (name 4, desc 2,
/// body 1). ID byte order resolves all ties, independent of input ordering.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord)]
pub struct Score {
    pub exact_name: bool,
    pub matched_query_terms: u16,
    pub field_weight: u16,
}

#[derive(Clone, Copy, Debug)]
pub struct Hit<'a> {
    pub id: &'a str,
    pub source_id: &'a str,
    pub sha256: &'a [u8; 32],
    pub score: Score,
    pub coverage: DocumentCoverage,
}

#[derive(Debug)]
pub struct SearchResult<'a> {
    pub snapshot: SnapshotKey,
    pub hits: Vec<Hit<'a>>,
    pub coverage: SearchCoverage,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Error {
    InvalidLimits,
    TooManySkills,
    InvalidField { input_index: usize, field: &'static str },
    InputByteBudget,
    MetadataByteBudget,
    DuplicateId,
    MetadataTermBudget,
    StaleSnapshot,
    TooManyCurrentSkills,
    DuplicateCurrentId,
    CurrentSkillMissing { input_index: usize },
    CurrentIdentityMismatch { input_index: usize },
    QueryTooLong,
    EmptyQuery,
    QueryTokenTooLong,
    TooManyQueryTerms,
    InvalidResultLimit,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // Bounded diagnostics: never echo untrusted IDs, text, bodies or queries.
        write!(f, "{self:?}")
    }
}
impl std::error::Error for Error {}

struct Term {
    text: Box<str>,
    fields: u8,
}

struct Entry {
    id: Box<str>,
    source_id: Box<str>,
    sha256: [u8; 32],
    name: Box<str>,
    terms: Box<[Term]>,
    coverage: DocumentCoverage,
}

/// Immutable per-snapshot facts. There is no cached eligible/disabled state.
/// Holding many old indices is a host-owned retention policy, not bounded here.
pub struct SkillIndex {
    key: SnapshotKey,
    limits: Limits,
    entries: Box<[Entry]>,
    statistics: IndexStatistics,
}

impl fmt::Debug for SkillIndex {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // Do not accidentally dump retained body vocabulary into debug logs.
        f.debug_struct("SkillIndex")
            .field("key", &self.key)
            .field("statistics", &self.statistics)
            .finish_non_exhaustive()
    }
}

impl SkillIndex {
    pub fn build(key: SnapshotKey, facts: &[SkillFacts<'_>], limits: Limits) -> Result<Self, Error> {
        limits.validate()?;
        if facts.len() > limits.max_skills {
            return Err(Error::TooManySkills);
        }
        // Check EVERY borrowed string length before scanning/tokenizing/cloning.
        // These caps bound this library's work; they cannot undo caller allocation.
        let mut input_bytes = 0;
        let mut metadata_bytes = 0;
        for (input_index, fact) in facts.iter().enumerate() {
            validate_identity(fact.id, fact.source_id, input_index)?;
            bounded_field(fact.name, MAX_NAME_BYTES, "name", input_index)?;
            bounded_field(fact.description, MAX_DESCRIPTION_BYTES, "description", input_index)?;
            let metadata = fact.id.len() + fact.source_id.len() + fact.name.len()
                + fact.description.len();
            metadata_bytes += metadata; // At most 128 already-bounded entries.
            if metadata_bytes > limits.max_metadata_bytes {
                return Err(Error::MetadataByteBudget);
            }
            let body_bytes = fact.body.map_or(0, |body| body.text.len());
            if body_bytes > HARD_MAX_INPUT_BODY_BYTES {
                return Err(Error::InvalidField { input_index, field: "body" });
            }
            input_bytes += metadata + body_bytes;
            if input_bytes > limits.max_input_bytes {
                return Err(Error::InputByteBudget);
            }
        }
        let mut ordered: Vec<_> = facts.iter().collect();
        ordered.sort_unstable_by(|a, b| a.id.cmp(b.id));
        if ordered.windows(2).any(|pair| pair[0].id == pair[1].id) {
            return Err(Error::DuplicateId);
        }
        let mut statistics = IndexStatistics {
            skills: facts.len(), validated_input_bytes: input_bytes, ..IndexStatistics::default()
        };
        let mut terms: Vec<BTreeMap<String, u8>> = Vec::with_capacity(facts.len());
        let mut coverages = Vec::with_capacity(facts.len());

        // Metadata for ALL skills goes first: early body entries cannot starve
        // later metadata. Metadata budget failure rejects the whole new index.
        for fact in &ordered {
            let mut map = BTreeMap::new();
            let mut coverage = DocumentCoverage::default();
            for (text, field) in [(fact.name, NAME), (fact.description, DESCRIPTION)] {
                let omitted = walk_tokens(text, true, |token| {
                    if insert_term(&mut map, token, field, limits, &mut statistics) {
                        Ok(())
                    } else {
                        Err(Error::MetadataTermBudget)
                    }
                })?;
                coverage.metadata_long_tokens_omitted += omitted;
            }
            terms.push(map);
            coverages.push(coverage);
        }

        let mut body_skills = 0;
        for ((fact, map), coverage) in ordered.iter().zip(&mut terms).zip(&mut coverages) {
            let Some(body) = fact.body else { continue };
            coverage.body_supplied = true;
            coverage.body_partial = true; // Remains true if a budget skips it.
            let remaining = limits.max_body_total_bytes - statistics.body_prefix_bytes;
            if body_skills == limits.max_body_skills {
                continue;
            }
            let mut end = body.text.len().min(limits.max_body_prefix_bytes).min(remaining);
            while !body.text.is_char_boundary(end) {
                end -= 1;
            }
            if end == 0 && !body.text.is_empty() {
                continue;
            }
            body_skills += 1;
            coverage.body_indexed = true;
            coverage.body_prefix_bytes = end;
            statistics.body_prefix_bytes += end;
            let complete = body.complete && end == body.text.len();
            let mut term_limited = false;
            let omitted = walk_tokens(&body.text[..end], complete, |token| {
                if !insert_term(map, token, BODY, limits, &mut statistics) {
                    term_limited = true;
                }
                Ok(())
            })?;
            coverage.body_partial = !complete || term_limited || omitted != 0;
        }

        let entries: Vec<_> = ordered.into_iter().zip(terms).zip(coverages)
            .map(|((fact, map), coverage)| {
                statistics.retained_identity_bytes += fact.id.len() + fact.source_id.len()
                    + fact.name.len();
                let terms: Vec<_> = map.into_iter().map(|(text, fields)| Term {
                    text: text.into_boxed_str(), fields,
                }).collect();
                Entry {
                    id: fact.id.into(), source_id: fact.source_id.into(), sha256: fact.sha256,
                    name: fact.name.into(), terms: terms.into_boxed_slice(), coverage,
                }
            }).collect();
        Ok(Self { key, limits, entries: entries.into_boxed_slice(), statistics })
    }

    pub fn snapshot_key(&self) -> SnapshotKey { self.key }

    /// Host diagnostics; do not surface excluded-source totals to an untrusted caller.
    pub fn statistics(&self) -> IndexStatistics { self.statistics }

    /// No stale fallback and no partial result on identity/scope validation failure.
    /// `current` is an allow-list of facts, not model-supplied selection arguments.
    pub fn search<'a>(
        &'a self,
        current_snapshot: SnapshotKey,
        current: &[CurrentSkill<'_>],
        query: &str,
        result_limit: usize,
    ) -> Result<SearchResult<'a>, Error> {
        if current_snapshot != self.key { return Err(Error::StaleSnapshot); }
        if current.len() > self.limits.max_skills { return Err(Error::TooManyCurrentSkills); }
        if query.len() > MAX_QUERY_BYTES { return Err(Error::QueryTooLong); }
        if result_limit == 0 || result_limit > MAX_RESULTS { return Err(Error::InvalidResultLimit); }

        // Validate even non-matching candidates before producing any rank output.
        let mut candidates = Vec::with_capacity(current.len());
        for (input_index, fact) in current.iter().enumerate() {
            validate_identity(fact.id, fact.source_id, input_index)?;
            let position = self.entries.binary_search_by(|entry| entry.id.as_ref().cmp(fact.id))
                .map_err(|_| Error::CurrentSkillMissing { input_index })?;
            let entry = &self.entries[position];
            if entry.source_id.as_ref() != fact.source_id || entry.sha256 != fact.sha256 {
                return Err(Error::CurrentIdentityMismatch { input_index });
            }
            candidates.push(position);
        }
        candidates.sort_unstable();
        if candidates.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err(Error::DuplicateCurrentId);
        }
        let mut query_terms = BTreeMap::new();
        let omitted = walk_tokens(query, true, |token| {
            if !query_terms.contains_key(token) {
                if query_terms.len() == MAX_QUERY_TERMS { return Err(Error::TooManyQueryTerms); }
                query_terms.insert(token.to_owned(), ());
            }
            Ok(())
        })?;
        if omitted != 0 { return Err(Error::QueryTokenTooLong); }
        if query_terms.is_empty() { return Err(Error::EmptyQuery); }

        let mut coverage = SearchCoverage::default();
        let mut hits = Vec::new();
        for position in candidates {
            let entry = &self.entries[position];
            coverage.eligible_skills += 1;
            coverage.metadata_partial_skills += usize::from(entry.coverage.metadata_long_tokens_omitted != 0);
            coverage.body_indexed_skills += usize::from(entry.coverage.body_indexed);
            coverage.metadata_only_skills += usize::from(!entry.coverage.body_indexed);
            coverage.body_partial_skills += usize::from(entry.coverage.body_indexed && entry.coverage.body_partial);
            coverage.body_budget_skipped_skills += usize::from(entry.coverage.body_supplied && !entry.coverage.body_indexed);
            let mut score = Score {
                exact_name: entry.name.eq_ignore_ascii_case(query.trim()), ..Score::default()
            };
            for token in query_terms.keys() {
                if let Ok(index) = entry.terms.binary_search_by(|term| term.text.as_ref().cmp(token.as_str())) {
                    let fields = entry.terms[index].fields;
                    score.matched_query_terms += 1;
                    score.field_weight += if fields & NAME != 0 { 4 }
                        else if fields & DESCRIPTION != 0 { 2 } else { 1 };
                }
            }
            if score.matched_query_terms != 0 || score.exact_name {
                hits.push(Hit {
                    id: &entry.id, source_id: &entry.source_id, sha256: &entry.sha256,
                    score, coverage: entry.coverage,
                });
            }
        }
        // All <=128 candidates are scored; output truncation never changes rank.
        hits.sort_unstable_by(|a, b| b.score.cmp(&a.score).then_with(|| a.id.cmp(b.id)));
        coverage.matched_skills = hits.len();
        hits.truncate(result_limit);
        coverage.returned_skills = hits.len();
        Ok(SearchResult { snapshot: self.key, hits, coverage })
    }
}

fn bounded_field(text: &str, max: usize, field: &'static str, input_index: usize) -> Result<(), Error> {
    // Length is checked before trim() can scan the string.
    if text.len() > max || text.is_empty() || text.trim().is_empty() {
        return Err(Error::InvalidField { input_index, field });
    }
    Ok(())
}

fn validate_identity(id: &str, source: &str, index: usize) -> Result<(), Error> {
    bounded_field(id, MAX_ID_BYTES, "id", index)?;
    bounded_field(source, MAX_SOURCE_BYTES, "source_id", index)
}

fn insert_term(
    map: &mut BTreeMap<String, u8>, token: &str, field: u8,
    limits: Limits, statistics: &mut IndexStatistics,
) -> bool {
    if let Some(fields) = map.get_mut(token) {
        *fields |= field;
        return true;
    }
    if map.len() == limits.max_terms_per_skill
        || statistics.retained_terms == limits.max_terms
        || token.len() > limits.max_term_bytes - statistics.retained_term_bytes
    {
        return false;
    }
    map.insert(token.to_owned(), field);
    statistics.retained_terms += 1;
    statistics.retained_term_bytes += token.len();
    true
}

/// Unicode lowercase, then alphanumeric runs (NOT case folding/NFKC/stemming).
/// Classify every emitted lowercase character, including expansions: U+0130
/// becomes i + U+0307, which must tokenize like an input already spelled i + mark.
/// Each scratch token is <=64 UTF-8 bytes even if lowercasing expands characters.
/// Long words are dropped whole; partial prefix words are never indexed as words.
fn walk_tokens(
    text: &str,
    final_token_complete: bool,
    mut visit: impl FnMut(&str) -> Result<(), Error>,
) -> Result<usize, Error> {
    let mut token = String::with_capacity(MAX_TOKEN_BYTES);
    let mut too_long = false;
    let mut omitted = 0;
    for ch in text.chars() {
        for lower in ch.to_lowercase() {
            if lower.is_alphanumeric() {
                if !too_long {
                    if token.len() + lower.len_utf8() <= MAX_TOKEN_BYTES {
                        token.push(lower);
                    } else {
                        too_long = true;
                    }
                }
            } else {
                if too_long { omitted += 1; }
                else if !token.is_empty() { visit(&token)?; }
                token.clear();
                too_long = false;
            }
        }
    }
    if final_token_complete {
        if too_long { omitted += 1; }
        else if !token.is_empty() { visit(&token)?; }
    }
    Ok(omitted)
}
