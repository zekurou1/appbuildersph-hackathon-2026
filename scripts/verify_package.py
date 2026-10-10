"""Test frozen executables from an unrelated working directory using synthetic originals."""
import argparse
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path("dist/OmniFindLocal"))
    parser.add_argument("--allow-unavailable-ocr", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve()
    cli = package / "OmniFindCLI.exe"
    assert cli.is_file()
    model = Path("models/minilm").resolve()
    destination = package / "models/minilm"
    shutil.copytree(model, destination, dirs_exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        corpus = run / "corpus"
        corpus.mkdir()
        text = corpus / "receipt.txt"
        text.write_text("Synthetic laptop receipt PKG-483. Power adapter costs 1250 pesos.")
        pdf = canvas.Canvas(str(corpus / "agreement.pdf"))
        pdf.drawString(40, 700, "Rental deposit returned thirty days after moving out.")
        pdf.save()
        image = Image.new("RGB", (1000, 350), "white")
        ImageDraw.Draw(image).text((40, 40), "Physics laboratory Wednesday SCH-846", fill="black",
            font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 32))
        image.save(corpus / "schedule.png")
        database = run / "data/index.sqlite"
        def invoke(*arguments):
            result = subprocess.run([str(cli), "--db", str(database), *map(str, arguments)], cwd=run,
                capture_output=True, text=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError(f"Packaged command failed: {arguments[0]} (exit {result.returncode})")
            return json.loads(result.stdout)
        rid = invoke("add-folder", corpus)["root_id"]
        coverage = invoke("refresh", rid)
        assert coverage["searchable"] >= 2, coverage
        result = invoke("search", "how soon do I get my rental deposit after leaving", "--type", "pdf")
        assert any(Path(r["path"]).name == "agreement.pdf" for r in result["results"])
        exact = invoke("search", "PKG-483")
        assert len(exact["results"]) == 1 and "PKG-483" in exact["results"][0]["text"]
        ocr = invoke("search", "SCH-846")
        ocr_ok = len(ocr["results"]) == 1 and ocr["results"][0]["provenance"] == "ocr-recognized"
        issues = invoke("issues", "--folder", rid)
        invoke("remove-folder", rid)
        assert not invoke("search", "PKG-483")["results"]
        assert text.exists()
        report = {"os": platform.platform(), "frozen_cli": True, "unrelated_working_directory": True,
                  "coverage": coverage, "pdf_semantic_search": True, "exact_code_and_restart": True,
                  "screenshot_ocr": ocr_ok, "issue_codes": [r["error"] for r in issues["items"]],
                  "root_removal_preserves_originals": True,
                  "limits": ["Automated executable checks, not independent user validation or package-identity certification",
                             "GUI launch and native controls require separate checks"]}
        output = Path("reports/runtime/package-verification.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        if not args.allow_unavailable_ocr:
            assert ocr_ok, "Packaged OCR did not succeed"


if __name__ == "__main__":
    main()
