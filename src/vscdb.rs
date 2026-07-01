//! Self-contained, pure-Rust, read-only SQLite reader for Cursor's `state.vscdb`.
//!
//! Cursor persists chat data in a SQLite KV store. Rather than depend on a
//! bundled C SQLite (which would break `windows_amd64_mingw` and add ~1 MB to
//! every build), we read the handful of `(key, value)` rows we need directly off
//! the SQLite file format. This module has **zero** new dependencies, compiles
//! cleanly on every target arch (it is plain Rust), and adds negligible binary
//! size.
//!
//! Only the read paths the Cursor parser actually exercises are implemented:
//!   * resolve a named table's root page via the `sqlite_master` schema (page 1),
//!   * scan a table b-tree (interior + leaf pages), and
//!   * decode the leaf-cell record, returning the `key` and `value` columns as
//!     raw bytes (the parser treats `value` as UTF-8 JSON).
//!
//! Large payloads (Cursor JSON blobs routinely spill) are reassembled across
//! overflow-page chains per the SQLite file format spec.
//!
//! WAL note: SQLite can journal in one of two modes. In the default *rollback*
//! mode every committed row lives in the main database file, so a main-file-only
//! reader like this one sees everything. In *WAL* (write-ahead logging) mode,
//! recent commits are appended to a separate `state.vscdb-wal` sidecar and only
//! folded ("checkpointed") into the main file later — a main-file-only reader
//! would miss any row still sitting in the `-wal`.
//!
//! Cursor uses rollback mode in practice: every observed `state.vscdb` has its
//! file-format version byte set to `1` (legacy/rollback) with no `-wal` sidecar.
//! That byte latches to `2` permanently once a file has ever been WAL, so `1`
//! means the file has never used WAL. This reader therefore targets rollback-mode
//! files and does not read `-wal` frames. The test fixture is generated in DELETE
//! journal mode (see `test/data_cursor/make_fixture.py`) to match.
//!
//! If a future Cursor build switches to WAL, supporting it is self-contained and
//! needs no refactor of the code below: in `open()`, when a non-empty
//! `state.vscdb-wal` exists, parse its 32-byte header + 24-byte-header frames,
//! validate the cumulative salt/checksum to find the valid frame set up to the
//! last commit, and overwrite the affected pages in `data` (extending it if a
//! commit grew the DB). The existing offset-based reader then runs unchanged over
//! the merged image. (A pure file reader cannot take SQLite's WAL read-lock, so
//! it reads an unlocked snapshot — fine for offline/idle Cursor.)
//!
//! Reference: <https://www.sqlite.org/fileformat2.html>

#![cfg(feature = "cursor")]

use std::fs;
use std::path::Path;

const HEADER_SIZE: usize = 100;

/// A decoded `(key, value)` row from a `(key TEXT, value BLOB/TEXT)` KV table.
pub struct KvRow {
    pub key: Vec<u8>,
    pub value: Vec<u8>,
}

/// An in-memory SQLite database file opened read-only.
pub struct VscDb {
    data: Vec<u8>,
    page_size: usize,
    /// Usable bytes per page = page_size - reserved_bytes_per_page.
    usable: usize,
}

impl VscDb {
    /// Open and slurp a SQLite file. Returns `None` if the file is missing or
    /// not a recognisable SQLite database (caller falls back to "no rows").
    pub fn open(path: &Path) -> Option<Self> {
        let data = fs::read(path).ok()?;
        if data.len() < HEADER_SIZE || &data[..16] != b"SQLite format 3\0" {
            return None;
        }

        // Page size: big-endian u16 at offset 16; the literal value 1 means 65536.
        let raw_page_size = u16::from_be_bytes([data[16], data[17]]) as usize;
        let page_size = if raw_page_size == 1 { 65536 } else { raw_page_size };
        if page_size < 512 || !page_size.is_power_of_two() {
            return None;
        }

        // Reserved bytes per page (byte 20), usually 0.
        let reserved = data[20] as usize;
        if reserved >= page_size {
            return None;
        }
        let usable = page_size - reserved;

        Some(VscDb {
            data,
            page_size,
            usable,
        })
    }

    /// Byte offset where 1-indexed page `n` begins.
    fn page_offset(&self, n: u32) -> usize {
        (n as usize - 1) * self.page_size
    }

    /// Read all rows of the named table.
    ///
    /// Resolves the table's root page from `sqlite_master`, then scans the b-tree.
    /// Records with fewer than two columns or non-text/blob `value` are decoded
    /// best-effort; rows that fail to decode are skipped rather than panicking.
    pub fn read_table(&self, table: &str) -> Vec<KvRow> {
        let root = match self.find_root_page(table) {
            Some(r) => r,
            None => return Vec::new(),
        };
        let mut out = Vec::new();
        let mut seen = std::collections::HashSet::new();
        self.scan_table_btree(root, &mut out, &mut seen);
        out
    }

    /// Walk `sqlite_master` (root page 1) for `name == table`, returning rootpage.
    ///
    /// `sqlite_master` columns: (type TEXT, name TEXT, tbl_name TEXT,
    /// rootpage INTEGER, sql TEXT). We match on `name` (col 1) and read
    /// `rootpage` (col 3). Root pages are never hardcoded.
    fn find_root_page(&self, table: &str) -> Option<u32> {
        let mut rows = Vec::new();
        let mut seen = std::collections::HashSet::new();
        self.scan_records(1, &mut rows, &mut seen);
        for rec in &rows {
            // col 1 = name, col 3 = rootpage
            let name = rec.get(1).and_then(|c| c.as_text());
            if name.as_deref() == Some(table) {
                if let Some(rp) = rec.get(3).and_then(|c| c.as_int()) {
                    if rp > 0 {
                        return Some(rp as u32);
                    }
                }
            }
        }
        None
    }

    /// Scan a table b-tree rooted at `page`, decoding each leaf record into a
    /// `KvRow` (col 0 = key, col 1 = value).
    fn scan_table_btree(
        &self,
        page: u32,
        out: &mut Vec<KvRow>,
        seen: &mut std::collections::HashSet<u32>,
    ) {
        let mut records = Vec::new();
        self.scan_records(page, &mut records, seen);
        for rec in records {
            let key = rec.first().map(|c| c.to_bytes()).unwrap_or_default();
            let value = rec.get(1).map(|c| c.to_bytes()).unwrap_or_default();
            out.push(KvRow { key, value });
        }
    }

    /// Recursively collect every leaf record (Vec<Value> per row) under `page`.
    fn scan_records(
        &self,
        page: u32,
        out: &mut Vec<Vec<Value>>,
        seen: &mut std::collections::HashSet<u32>,
    ) {
        // Cycle / corruption guard.
        if page == 0 || !seen.insert(page) {
            return;
        }
        let base = self.page_offset(page);
        if base + 8 > self.data.len() {
            return;
        }
        // Page 1 carries the 100-byte database header before its b-tree header.
        let hdr = if page == 1 { base + HEADER_SIZE } else { base };
        let page_type = self.data[hdr];
        let cell_count = u16::from_be_bytes([self.data[hdr + 3], self.data[hdr + 4]]) as usize;

        match page_type {
            0x0d => {
                // Leaf table page. Cell pointer array starts after the 8-byte header.
                let ptr_array = hdr + 8;
                for i in 0..cell_count {
                    let p = ptr_array + i * 2;
                    if p + 2 > self.data.len() {
                        break;
                    }
                    let cell_off =
                        base + u16::from_be_bytes([self.data[p], self.data[p + 1]]) as usize;
                    if let Some(rec) = self.decode_leaf_cell(cell_off) {
                        out.push(rec);
                    }
                }
            }
            0x05 => {
                // Interior table page: 12-byte header, right-most child at offset 8.
                let ptr_array = hdr + 12;
                for i in 0..cell_count {
                    let p = ptr_array + i * 2;
                    if p + 2 > self.data.len() {
                        break;
                    }
                    let cell_off =
                        base + u16::from_be_bytes([self.data[p], self.data[p + 1]]) as usize;
                    if cell_off + 4 <= self.data.len() {
                        let child = u32::from_be_bytes([
                            self.data[cell_off],
                            self.data[cell_off + 1],
                            self.data[cell_off + 2],
                            self.data[cell_off + 3],
                        ]);
                        self.scan_records(child, out, seen);
                    }
                }
                // Right-most child pointer.
                if hdr + 12 <= self.data.len() {
                    let right = u32::from_be_bytes([
                        self.data[hdr + 8],
                        self.data[hdr + 9],
                        self.data[hdr + 10],
                        self.data[hdr + 11],
                    ]);
                    self.scan_records(right, out, seen);
                }
            }
            // 0x0a (index leaf) / 0x02 (index interior) are ignored for table scans.
            _ => {}
        }
    }

    /// Decode a table-leaf cell at `cell_off` into a record (Vec<Value>),
    /// reassembling the payload across overflow pages when it spills.
    fn decode_leaf_cell(&self, cell_off: usize) -> Option<Vec<Value>> {
        let mut pos = cell_off;
        let (payload_len, n1) = read_varint(&self.data, pos)?;
        pos += n1;
        // rowid varint (unused — record carries its own columns)
        let (_rowid, n2) = read_varint(&self.data, pos)?;
        pos += n2;

        let payload_len = payload_len as usize;
        let payload = self.read_payload(pos, payload_len, /*table_leaf=*/ true)?;
        decode_record(&payload)
    }

    /// Read `payload_len` bytes of record payload starting at `start`, following
    /// the overflow-page chain if the payload does not fit on the page.
    ///
    /// Overflow threshold math (SQLite spec, table b-tree leaf):
    ///   X = usable - 35
    ///   if P <= X            => entire payload on page
    ///   else
    ///     M = ((usable - 12) * 32 / 255) - 23
    ///     K = M + ((P - M) % (usable - 4))
    ///     local = if K <= X { K } else { M }
    /// The remaining `P - local` bytes chain through overflow pages; each overflow
    /// page begins with a 4-byte BE next-page number (0 = last) then content.
    fn read_payload(&self, start: usize, p: usize, table_leaf: bool) -> Option<Vec<u8>> {
        // A payload can never legitimately exceed the file itself. Reject an
        // out-of-range length up front so a corrupt varint cannot drive a huge
        // `Vec::with_capacity(p)` allocation (which would abort the process).
        if p > self.data.len() {
            return None;
        }
        let usable = self.usable;
        let x = if table_leaf {
            usable - 35
        } else {
            ((usable - 12) * 64 / 255) - 23
        };

        if p <= x {
            // Fits entirely on the page.
            if start + p > self.data.len() {
                return None;
            }
            return Some(self.data[start..start + p].to_vec());
        }

        let m = ((usable - 12) * 32 / 255) - 23;
        let k = m + ((p - m) % (usable - 4));
        let local = if k <= x { k } else { m };

        if start + local + 4 > self.data.len() {
            return None;
        }
        let mut out = Vec::with_capacity(p);
        out.extend_from_slice(&self.data[start..start + local]);

        // 4-byte BE overflow page number immediately after the local payload.
        let mut next = u32::from_be_bytes([
            self.data[start + local],
            self.data[start + local + 1],
            self.data[start + local + 2],
            self.data[start + local + 3],
        ]);

        let mut remaining = p - local;
        let mut guard = 0usize;
        let max_pages = self.data.len() / self.page_size + 2;
        while next != 0 && remaining > 0 {
            guard += 1;
            if guard > max_pages {
                break; // corrupt / cyclic chain
            }
            let off = self.page_offset(next);
            if off + 4 > self.data.len() {
                break;
            }
            let nxt = u32::from_be_bytes([
                self.data[off],
                self.data[off + 1],
                self.data[off + 2],
                self.data[off + 3],
            ]);
            let avail = (self.usable - 4).min(remaining);
            let content_start = off + 4;
            if content_start + avail > self.data.len() {
                break;
            }
            out.extend_from_slice(&self.data[content_start..content_start + avail]);
            remaining -= avail;
            next = nxt;
        }
        Some(out)
    }
}

/// A single decoded SQLite record column value (only the variants we need).
enum Value {
    Null,
    Int(i64),
    Real(f64),
    Text(Vec<u8>),
    Blob(Vec<u8>),
}

impl Value {
    fn as_text(&self) -> Option<String> {
        match self {
            Value::Text(b) => Some(String::from_utf8_lossy(b).into_owned()),
            _ => None,
        }
    }

    fn as_int(&self) -> Option<i64> {
        match self {
            Value::Int(i) => Some(*i),
            _ => None,
        }
    }

    /// Return TEXT/BLOB bodies as raw bytes; numeric/null collapse to empty.
    fn to_bytes(&self) -> Vec<u8> {
        match self {
            Value::Text(b) | Value::Blob(b) => b.clone(),
            Value::Int(i) => i.to_string().into_bytes(),
            Value::Real(r) => r.to_string().into_bytes(),
            Value::Null => Vec::new(),
        }
    }
}

/// Decode a SQLite record (header of serial types + column bodies) into values.
fn decode_record(payload: &[u8]) -> Option<Vec<Value>> {
    let (header_len, n) = read_varint(payload, 0)?;
    let header_len = header_len as usize;
    if header_len > payload.len() {
        return None;
    }

    // Read serial types from the header region.
    let mut serials = Vec::new();
    let mut hpos = n;
    while hpos < header_len {
        let (st, sn) = read_varint(payload, hpos)?;
        serials.push(st);
        hpos += sn;
    }

    // Column bodies start right after the header.
    let mut body = header_len;
    let mut values = Vec::with_capacity(serials.len());
    for st in serials {
        let (val, consumed) = decode_serial(st, payload, body)?;
        body += consumed;
        values.push(val);
    }
    Some(values)
}

/// Decode one column body given its serial type. Returns (value, bytes consumed).
fn decode_serial(st: u64, data: &[u8], pos: usize) -> Option<(Value, usize)> {
    let read = |len: usize| -> Option<&[u8]> {
        if pos + len <= data.len() {
            Some(&data[pos..pos + len])
        } else {
            None
        }
    };
    let val = match st {
        0 => (Value::Null, 0),
        1 => (Value::Int(read(1)?[0] as i8 as i64), 1),
        2 => {
            let b = read(2)?;
            (Value::Int(i16::from_be_bytes([b[0], b[1]]) as i64), 2)
        }
        3 => {
            let b = read(3)?;
            let mut v = ((b[0] as i64) << 16) | ((b[1] as i64) << 8) | (b[2] as i64);
            if v & 0x80_0000 != 0 {
                v -= 1 << 24; // sign-extend 24-bit
            }
            (Value::Int(v), 3)
        }
        4 => {
            let b = read(4)?;
            (
                Value::Int(i32::from_be_bytes([b[0], b[1], b[2], b[3]]) as i64),
                4,
            )
        }
        5 => {
            let b = read(6)?;
            let mut v = 0i64;
            for &byte in b {
                v = (v << 8) | byte as i64;
            }
            if v & 0x8000_0000_0000 != 0 {
                v -= 1 << 48; // sign-extend 48-bit
            }
            (Value::Int(v), 6)
        }
        6 => {
            let b = read(8)?;
            (
                Value::Int(i64::from_be_bytes([
                    b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
                ])),
                8,
            )
        }
        7 => {
            let b = read(8)?;
            (
                Value::Real(f64::from_be_bytes([
                    b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
                ])),
                8,
            )
        }
        8 => (Value::Int(0), 0),
        9 => (Value::Int(1), 0),
        n if n >= 12 && n % 2 == 0 => {
            let len = ((n - 12) / 2) as usize;
            (Value::Blob(read(len)?.to_vec()), len)
        }
        n if n >= 13 => {
            let len = ((n - 13) / 2) as usize;
            (Value::Text(read(len)?.to_vec()), len)
        }
        // 10 and 11 are reserved/internal serial types — treat as empty.
        _ => (Value::Null, 0),
    };
    Some(val)
}

/// Read a SQLite varint (big-endian, 1–9 bytes; high bit = continuation; the 9th
/// byte contributes all 8 bits). Returns (value, bytes consumed).
fn read_varint(data: &[u8], start: usize) -> Option<(u64, usize)> {
    let mut result: u64 = 0;
    let mut i = 0;
    while i < 9 {
        let byte = *data.get(start + i)?;
        if i == 8 {
            // 9th byte: use all 8 bits.
            result = (result << 8) | byte as u64;
            return Some((result, 9));
        }
        result = (result << 7) | (byte & 0x7f) as u64;
        if byte & 0x80 == 0 {
            return Some((result, i + 1));
        }
        i += 1;
    }
    Some((result, 9))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn fixture() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("test")
            .join("data_cursor")
            .join("state.vscdb")
    }

    #[test]
    fn varint_roundtrip_basics() {
        assert_eq!(read_varint(&[0x00], 0), Some((0, 1)));
        assert_eq!(read_varint(&[0x7f], 0), Some((127, 1)));
        assert_eq!(read_varint(&[0x81, 0x00], 0), Some((128, 2)));
        assert_eq!(read_varint(&[0x82, 0x2c], 0), Some((300, 2)));
    }

    #[test]
    fn opens_fixture_and_reads_cursordiskkv() {
        let db = VscDb::open(&fixture()).expect("fixture should open as a SQLite db");
        let rows = db.read_table("cursorDiskKV");

        // The fixture has 3 conversation rows + 2 noise rows = 5 total.
        assert_eq!(rows.len(), 5, "expected 5 cursorDiskKV rows");

        let keys: Vec<String> = rows
            .iter()
            .map(|r| String::from_utf8_lossy(&r.key).into_owned())
            .collect();

        // composerData / bubbleId rows are present and decodable.
        let composer: Vec<_> = keys
            .iter()
            .filter(|k| k.starts_with("composerData:"))
            .collect();
        assert_eq!(composer.len(), 1, "exactly one composerData row");

        let bubbles: Vec<_> = keys.iter().filter(|k| k.starts_with("bubbleId:")).collect();
        assert_eq!(bubbles.len(), 2, "exactly two bubbleId rows");

        // Values are valid UTF-8 JSON the parser can consume.
        for r in &rows {
            if String::from_utf8_lossy(&r.key).starts_with("composerData:") {
                let v: serde_json::Value =
                    serde_json::from_slice(&r.value).expect("composer value is JSON");
                assert_eq!(v["composerId"], "comp-1111-0000-0000-0000-000000000001");
            }
        }
    }

    #[test]
    fn unknown_table_returns_empty() {
        let db = VscDb::open(&fixture()).unwrap();
        assert!(db.read_table("no_such_table").is_empty());
    }

    #[test]
    fn missing_file_returns_none() {
        assert!(VscDb::open(Path::new("/nonexistent/state.vscdb")).is_none());
    }
}
