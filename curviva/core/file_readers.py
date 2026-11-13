"""core 域 / 多格式数据文件读取（CSV / TXT / DAT / TSV / ASC / Excel）。

对标 Origin 的「导入向导」后端，全部返回与文件格式无关的**表格描述 spec**：

    {
      "name": "文件名", "path": "...", "encoding": "utf-8-sig",
      "delimiter": "\\t", "header": ["x", "y"],
      "meta": {"x": {"long_name": "时间", "unit": "s", "comment": "", ...}},
      "rows": [[...], [...]],          # 纯数据行（不含表头与元数据行）
      "raw_lines": [...],              # 预览用的原始有效行
    }

DataManager 只消费 spec，不关心文件类型；新增格式只需在此加一个 reader。
"""

import csv
import os
import re
from collections import Counter

TEXT_EXTS = {".csv", ".txt", ".dat", ".tsv", ".asc", ".xy", ".xye", ".prn", ".out"}
EXCEL_EXTS = {".xlsx", ".xlsm"}
LEGACY_XLS_EXTS = {".xls"}
DATA_EXTS = TEXT_EXTS | EXCEL_EXTS

DATA_FILE_FILTER = (
    "全部数据文件 (*.csv *.txt *.dat *.tsv *.asc *.xy *.xye *.prn *.out *.xlsx *.xlsm);;"
    "CSV 表格 (*.csv);;"
    "文本 / 数据文件 (*.txt *.dat *.tsv *.asc *.xy *.xye *.prn *.out);;"
    "Excel 工作簿 (*.xlsx *.xlsm);;"
    "所有文件 (*.*)"
)

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "latin-1")

DELIMITER_CHOICES = [
    ("自动识别", "auto"), ("制表符 Tab", "\t"), ("逗号 ,", ","),
    ("分号 ;", ";"), ("竖线 |", "|"), ("空白 / 空格", "whitespace"),
]
ENCODING_CHOICES = [("自动识别", "auto"), ("UTF-8", "utf-8-sig"),
                    ("GBK / GB18030", "gb18030"), ("Big5", "big5"),
                    ("Latin-1", "latin-1")]

META_LABELS = {
    "longname": "long_name", "long name": "long_name", "long_name": "long_name",
    "长名称": "long_name", "名称": "long_name",
    "unit": "unit", "units": "unit", "单位": "unit",
    "comment": "comment", "comments": "comment", "注释": "comment", "说明": "comment",
    "f(x)": "formula", "f(x)=": "formula", "formula": "formula", "公式": "formula",
}
META_ORDER = ("long_name", "unit", "comment", "formula")
META_KEYS = set(META_ORDER)


def extension(path: str) -> str:
    return os.path.splitext(str(path))[1].lower()


def is_excel(path: str) -> bool:
    return extension(path) in EXCEL_EXTS


def is_supported(path: str) -> bool:
    return extension(path) in DATA_EXTS


def _can_float(text) -> bool:
    try:
        float(str(text).strip())
        return True
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------
# 编码与分隔符
# ------------------------------------------------------------------

def decode_text_file(path: str, encoding: str = "auto") -> tuple:
    """读取文本并按编码解码；返回 (文本, 实际编码)。"""
    with open(path, "rb") as f:
        raw = f.read()
    if encoding and encoding != "auto":
        return raw.decode(encoding, errors="replace"), encoding
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
            return text, ("utf-8-sig" if enc in ("utf-8-sig", "utf-8") else enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1"


def split_line(line: str, delimiter: str) -> list:
    """按分隔符切一行；空白模式支持任意连续空白。"""
    line = line.rstrip("\r\n")
    if delimiter == "whitespace":
        return re.split(r"\s+", line.strip()) if line.strip() else []
    if delimiter == "\t":
        return line.split("\t")
    try:
        return next(csv.reader([line], delimiter=delimiter))
    except (csv.Error, StopIteration):
        return line.split(delimiter)


def detect_delimiter(lines: list) -> str:
    """优先采用在多数行中稳定出现的显式分隔符，最后才退回空白分隔。"""
    sample = [l for l in lines if l.strip()][:25]
    if not sample:
        return "whitespace"
    for cand in ("\t", ",", ";", "|"):
        rate = sum(1 for l in sample if cand in l) / len(sample)
        if rate < 0.6:
            continue
        counts = [len(split_line(l, cand)) for l in sample]
        if max(counts) < 2:
            continue
        mode = Counter(counts).most_common(1)[0][1]
        if mode >= max(2, int(len(sample) * 0.7)):
            return cand
    return "whitespace"


def _meta_label(cell) -> str:
    key = str(cell).strip().lower().rstrip(":：").strip()
    key = key.replace(" ", "").replace("_", "")
    return META_LABELS.get(key, "")


def _clean_header(names: list) -> list:
    out, used = [], set()
    for i, raw in enumerate(names):
        name = str(raw).strip() or f"列{i + 1}"
        final, n = name, 2
        while final in used:
            final = f"{name}_{n}"
            n += 1
        used.add(final)
        out.append(final)
    return out


# ------------------------------------------------------------------
# 通用二维表解析（文本 / Excel 共用）
# ------------------------------------------------------------------

def parse_rows(rows: list, name: str = "数据", header="auto",
               meta_rows="auto") -> dict:
    """把二维字符串表解析为 spec：表头、Origin 式元数据行、纯数据行。"""
    rows = [[("" if v is None else str(v).strip()) for v in r] for r in rows if r]
    rows = [r for r in rows if any(str(v).strip() != "" for v in r)]
    if not rows:
        raise ValueError("文件中没有可用数据。")

    # 表头：auto 时按「首行是否含数字」判断。
    # 注意：Origin 的元数据行形如「Long Name<TAB>列1名<TAB>列2名」，比表头多一格，
    # 因此列数必须以表头为准，不能取所有行的最大宽度。
    first = rows[0]
    if header == "auto":
        has_header = not any(_can_float(v) for v in first if str(v).strip() != "")
    else:
        has_header = bool(header)
    if has_header:
        cols = _clean_header(first)
        body = rows[1:]
    else:
        data_rows = [r for r in rows if not _meta_label(r[0])]
        ncols = max((len(r) for r in (data_rows or rows)), default=1)
        cols = _clean_header([f"列{i + 1}" for i in range(ncols)])
        body = rows

    # 元数据行：auto = 识别带标签的 Long Name / Units / Comments / F(x)= 行
    meta = {c: {"long_name": "", "unit": "", "comment": "",
                "formula": "", "designation": ""} for c in cols}
    consumed = 0
    if meta_rows == "auto":
        while body and consumed < 6:
            key = _meta_label(body[0][0])
            if not key:
                break
            row = body[0]
            values = [str(v).strip() for v in row[1:]]
            if len(values) >= len(cols):
                pairs = zip(cols, values)        # 标签后跟每列一个值（n+1 格）
            else:
                pairs = zip(cols[1:], values)    # 标签占用第一列格位（n 格）
            for c, value in pairs:
                meta[c][key] = value
            body = body[1:]
            consumed += 1
    elif meta_rows:
        n = int(meta_rows)
        for i in range(min(n, len(body))):
            key = META_ORDER[i] if i < len(META_ORDER) else "comment"
            row = body[i]
            for j, c in enumerate(cols):
                meta[c][key] = str(row[j]).strip() if j < len(row) else ""
        body = body[n:]
        consumed = n

    ncols = len(cols)
    body = [[(r[j] if j < len(r) else "") for j in range(ncols)] for r in body]
    return {"name": name, "header": cols, "meta": meta, "rows": body,
            "meta_lines": consumed, "has_header": has_header,
            "encoding": "", "delimiter": "", "path": "", "raw_lines": []}


def parse_text(text: str, options: dict = None, name: str = "数据") -> dict:
    """解析文本（可由文件读入，也可来自剪贴板）。"""
    opt = options or {}
    comment = str(opt.get("comment", "#,!,//,%")).strip()
    prefixes = [p.strip() for p in comment.split(",") if p.strip()]
    skip = max(0, int(opt.get("skip_rows", 0) or 0))
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[0].startswith("\ufeff"):
        lines[0] = lines[0].lstrip("\ufeff")
    kept = []
    for i, line in enumerate(lines):
        if i < skip or not line.strip():
            continue
        if any(line.lstrip().startswith(p) for p in prefixes):
            continue
        kept.append(line.rstrip("\r\n"))
    delim = opt.get("delimiter", "auto") or "auto"
    if delim == "auto":
        delim = detect_delimiter(kept)
    table = [split_line(l, delim) for l in kept]
    spec = parse_rows(table, name=name, header=opt.get("header", "auto"),
                      meta_rows=opt.get("meta_rows", "auto"))
    spec.update({"delimiter": delim, "raw_lines": kept[:40],
                 "encoding": opt.get("encoding", "auto")})
    return spec


def read_text_file(path: str, options: dict = None) -> dict:
    opt = options or {}
    text, enc = decode_text_file(path, opt.get("encoding", "auto"))
    parse_opt = {**opt, "encoding": enc}
    spec = parse_text(text, parse_opt,
                      name=os.path.splitext(os.path.basename(path))[0])
    spec.update({"path": path, "encoding": enc})
    return spec


def read_excel_file(path: str, sheet_names=None, options: dict = None) -> list:
    """每个选中工作表返回一个 spec（与文本读取结构一致）。"""
    from openpyxl import load_workbook
    opt = options or {}
    wb = load_workbook(path, read_only=True, data_only=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    targets = wb.sheetnames if sheet_names is None else \
        [s for s in sheet_names if s in wb.sheetnames]
    specs = []
    for sn in targets:
        ws = wb[sn]
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = []
            for v in row:
                if v is None:
                    cells.append("")
                elif isinstance(v, bool):
                    cells.append(str(v))
                elif isinstance(v, float) and v.is_integer():
                    cells.append(str(int(v)))
                else:
                    cells.append(str(v))
            rows.append(cells)
        rows = [r for r in rows if any(str(c).strip() != "" for c in r)]
        if not rows:
            continue
        ncols = max(len(r) for r in rows)
        rows = [r + [""] * (ncols - len(r)) for r in rows]
        try:
            spec = parse_rows(rows, name=f"{stem}-{sn}",
                              header=opt.get("header", "auto"),
                              meta_rows=opt.get("meta_rows", "auto"))
        except ValueError:
            continue
        spec.update({"path": path, "encoding": "xlsx", "delimiter": "excel",
                     "raw_lines": [" | ".join(r) for r in rows[:40]]})
        specs.append(spec)
    wb.close()
    if not specs:
        raise ValueError("所选工作表中没有可用数据。")
    return specs


def read_any(path: str, options: dict = None, sheet_names=None) -> list:
    """按扩展名自动分派；统一返回 spec 列表。"""
    ext = extension(path)
    if ext in LEGACY_XLS_EXTS:
        raise ValueError("暂不支持旧版 .xls，请先另存为 .xlsx 后再打开。")
    if ext in EXCEL_EXTS:
        return read_excel_file(path, sheet_names, options)
    if ext in TEXT_EXTS or not ext:
        return [read_text_file(path, options)]
    # 未知扩展名按文本尝试，兼容 .csv.gz 之外的自定义数据文件
    return [read_text_file(path, options)]


def default_options() -> dict:
    return {"encoding": "auto", "delimiter": "auto", "comment": "#,!,//,%",
            "skip_rows": 0, "header": "auto", "meta_rows": "auto"}
