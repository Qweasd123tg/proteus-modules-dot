//! Research adapter, not an AppServer startup path. Input contract: ordered display
//! facts from one *fully, strictly validated* immutable snapshot, with exact spans
//! from its private JSONL staging file. Never substitute this for strict recovery.
use anyhow::{Result, ensure};
use std::{
    collections::VecDeque,
    fs::File,
    io::{BufWriter, Read, Seek, SeekFrom, Write},
};

use crate::{
    core::{HistoryMutationKind, JournalEntry, JournalRecord, TurnSettlementStatus},
    domain::{PartId, TurnId},
    model_standard::{ContentPart, PartScope},
};
use super::{AppTranscriptMessage, TranscriptRows, append_transcript_message};

const RETAINED_PARTS: usize = 512;
const PAGE_ROWS: usize = 50;
const MAX_SPAN: u64 = 256 << 10;
const MAX_STAGE: u64 = 512 << 20;
const MAX_INDEX_BYTES: u64 = 16 << 20;
const ENTRY_BYTES: u64 = 24;

pub(super) struct Proof {
    index: BufWriter<File>,
    entries: u64,
    rows: u64,
    recent: VecDeque<PartId>,
    compacted: bool,
}

impl Proof {
    pub(super) fn new(live: Option<TurnId>) -> Result<Option<Self>> {
        if live.is_some() { return Ok(None); }
        Ok(Some(Self {
            index: BufWriter::new(tempfile::tempfile()?),
            entries: 0, rows: 0, recent: VecDeque::new(), compacted: false,
        }))
    }

    // A false result permanently disqualifies this projection (the caller drops
    // the Proof), never just this record. Continue full validation and staging.
    pub(super) fn observe(&mut self, r: &JournalRecord, offset: u64, len: u64) -> Result<bool> {
        if offset.checked_add(len).is_none_or(|end| end > MAX_STAGE) { return Ok(false); }
        let m = match &r.entry {
            JournalEntry::HistoryMutated(m) => m,
            JournalEntry::TurnOpened(_) => return Ok(true),
            JournalEntry::TurnSettled(s) if s.status == TurnSettlementStatus::Success => return Ok(true),
            _ => return Ok(false),
        };
        match m.mutation {
            HistoryMutationKind::Replace if m.compaction.is_some() => {
                // All explicitly seen parts have already passed dedup, even when
                // blank. Rehosting them cannot add a row or move their dates.
                // Use a fixed *positive* witness. No Bloom or guessed identity.
                self.compacted = true;
                return Ok(m.messages.iter().flat_map(|m| &m.parts).all(|p| self.recent.contains(&p.part_id)));
            }
            // Before the first compaction, strict active-history uniqueness
            // rules out any repeat across batches. Afterwards old, inactive
            // identities could return: do not accept even apparently new text.
            HistoryMutationKind::Append if !self.compacted && m.compaction.is_none() => {}
            _ => return Ok(false),
        }

        let mut n = 0u64;
        for message in &m.messages {
            let [p] = message.parts.as_slice() else { return Ok(false) };
            let ContentPart::Text { text } = &p.payload else { return Ok(false) };
            if p.scope != PartScope::Conversation { return Ok(false); }
            n += u64::from(!text.trim().is_empty());
            if self.recent.len() == RETAINED_PARTS { self.recent.pop_front(); }
            self.recent.push_back(p.part_id);
        }
        if n == 0 { return Ok(true); }
        if len > MAX_SPAN || self.entries >= MAX_INDEX_BYTES / ENTRY_BYTES { return Ok(false); }
        self.rows = self.rows.checked_add(n).ok_or_else(|| anyhow::anyhow!("row count overflow"))?;
        for x in [self.rows, offset, len] { self.index.write_all(&x.to_le_bytes())?; }
        self.entries += 1;
        Ok(true)
    }

    // Hand off the very same anonymous data file, *after* strict validation of
    // the fixed source and successful flush. Not a reopened path / journal head.
    pub(super) fn seal(self, data: File) -> Result<PlainPages> {
        Ok(PlainPages {
            data, index: self.index.into_inner()?, entries: self.entries, rows: self.rows
        })
    }
}

pub(super) struct PlainPages { data: File, index: File, entries: u64, pub(super) rows: u64 }

impl PlainPages {
    fn span(&mut self, entry: u64) -> Result<(u64,u64,u64)> {
        ensure!(entry < self.entries, "invalid archive span");
        self.index.seek(SeekFrom::Start(entry * ENTRY_BYTES))?;
        let mut b = [0; ENTRY_BYTES as usize];
        self.index.read_exact(&mut b)?;
        let word = |at: usize| u64::from_le_bytes(b[at..at+8].try_into().unwrap());
        Ok((word(0),word(8),word(16)))
    }

    // Return exact requested page. Metrics are diagnostics for this study.
    pub(super) fn page(&mut self, before: u64, limit: usize) -> Result<(Vec<AppTranscriptMessage>, u64, u64)> {
        ensure!(limit <= PAGE_ROWS, "window exceeds page limit");
        ensure!(before <= self.rows, "cursor beyond immutable archive");
        let start = before.saturating_sub(limit as u64);
        let mut out = TranscriptRows::default();
        let (mut reads, mut bytes) = (0, 0);
        if before == start { return Ok((out.rows, reads, bytes)); }

        let (mut low, mut high) = (0, self.entries);
        while low < high {
            let mid = low + (high-low)/2;
            if self.span(mid)?.0 <= start { low = mid+1; } else { high = mid; }
        }
        let mut at = if low == 0 { 0 } else { self.span(low-1)?.0 };
        while at < before {
            let (end, offset, len) = self.span(low)?;
            ensure!(end > at && end <= self.rows, "invalid cumulative row count");
            ensure!(len <= MAX_SPAN && offset.checked_add(len).is_some_and(|end| end <= MAX_STAGE), "invalid staged byte range");
            self.data.seek(SeekFrom::Start(offset))?;
            let size = usize::try_from(len)?;
            let mut buf = vec![0;size];
            self.data.read_exact(&mut buf)?;
            let record: JournalRecord = serde_json::from_slice(&buf)?;
            let JournalEntry::HistoryMutated(m) = record.entry else { anyhow::bail!("unexpected staged record") };
            ensure!(m.mutation == HistoryMutationKind::Append, "unexpected staged mutation");
            let mut index = at;
            for message in &m.messages {
                let [p] = message.parts.as_slice() else { anyhow::bail!("unexpected staged parts") };
                let ContentPart::Text { text } = &p.payload else { anyhow::bail!("unexpected staged payload") };
                if text.trim().is_empty() { continue; }
                if (start..before).contains(&index) {
                    append_transcript_message(&mut out, message);
                    out.rows.last_mut().expect("nonblank text produced a row").timestamp_ms = Some(record.timestamp_ms);
                }
                index += 1;
            }
            ensure!(index == end, "staged row count changed");
            at=end; low+=1; reads+=1; bytes+=len;
        }
        ensure!(out.rows.len() as u64 == before-start,"incomplete page");
        Ok((out.rows,reads,bytes))
    }
}
