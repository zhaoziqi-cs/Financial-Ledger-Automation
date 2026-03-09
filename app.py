from pathlib import Path
from io import BytesIO
import tempfile
import os

from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename

from etl.parse_bank_flow import parse_bank_flow
from etl.update_ledger import update_ledger


BASE_DIR = Path(__file__).resolve().parent
MAP_FILE = BASE_DIR / "data" / "config" / "project_map.xlsx"
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024


def _allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/process")
def process_files():
    ledger_upload = request.files.get("ledger_file")
    bank_flow_upload = request.files.get("bank_flow_file")

    if not ledger_upload or not bank_flow_upload:
        return render_template("index.html", error="请上传银行日记账和银行流水两个文件。"), 400

    if not ledger_upload.filename or not bank_flow_upload.filename:
        return render_template("index.html", error="上传文件名不能为空。"), 400

    if not _allowed_file(ledger_upload.filename) or not _allowed_file(bank_flow_upload.filename):
        return render_template("index.html", error="仅支持 .xlsx / .xls 文件。"), 400

    if not MAP_FILE.exists():
        return render_template("index.html", error="缺少项目映射文件：data/config/project_map.xlsx"), 500

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        ledger_path = temp_path / secure_filename(ledger_upload.filename)
        bank_flow_path = temp_path / secure_filename(bank_flow_upload.filename)
        parsed_path = temp_path / "bank_flow_parsed.xlsx"
        output_path = temp_path / "ledger.xlsx"

        ledger_upload.save(ledger_path)
        bank_flow_upload.save(bank_flow_path)

        try:
            parse_bank_flow(str(bank_flow_path), str(MAP_FILE), str(parsed_path))
            update_ledger(
                ledger_file=str(ledger_path),
                bank_file=str(parsed_path),
                output_file=str(output_path),
                backup=False
            )
        except Exception as exc:
            return render_template("index.html", error=f"处理失败：{exc}"), 500

        output_bytes = output_path.read_bytes()

        return send_file(
            BytesIO(output_bytes),
            as_attachment=True,
            download_name="ledger.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
