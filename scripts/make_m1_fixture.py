"""Original, redistributable Chinese text PDF; no external source material."""

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / "apps/web/public/original-handbook.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdf = canvas.Canvas(str(target), pagesize=(595, 842), invariant=True)
    pdf.setTitle("CiteWeave 原创验收手册")
    pdf.setAuthor("CiteWeave original synthetic fixture")
    pages = [
        [
            "湖畔观测站 / 采样与保留",
            "这是一份原创合成材料，用于验证知识库入库、问答和证据定位。",
            "湖畔观测站的温度传感器每 30 秒采样一次，原始数据在本地保留 7 天。",
            "湖畔观测站的湿度传感器每 60 秒采样一次，记录统一使用北京时间。",
            "每日凌晨两点汇总观测数据，汇总报告保存 90 天。",
            "设备维护窗口为每周三下午三点到四点，维护时暂停采样。",
            "设备编号采用 STATION-LAKE 加三位数字，例如 STATION-LAKE-007。",
            "当温度连续三次超过 38 摄氏度时，系统发送一次高温提醒。",
            "提醒只说明合成观测事件，不代表真实天气预报或安全建议。",
            *[f"巡检项目 {i:02}：检查观测站接线和时钟，完成后记录检查结果。" for i in range(1, 18)],
        ],
        [
            "山丘观测站 / 恢复与证据",
            "山丘观测站每 15 秒采集一次风速，原始记录保留 14 天。",
            "山丘观测站的风向读数每 45 秒更新一次，汇总报告保留 180 天。",
            "CiteWeave 任务租约过期后会自动重新派发，最多尝试 3 次。",
            "只有完成索引校验并提交 READY 状态的版本，才进入查询可见范围。",
            "旧任务写入独立的暂存索引，不能覆盖新任务已经发布的有效版本。",
            "引用记录文件版本、原文片段、页码和字符边界框，支持点击定位。",
            "原文引用准确并不等于答案语义一定正确，用户仍需核对证据。",
            "本手册全部内容为个人项目独立编写，允许用于开源演示与自动化测试。",
            *[f"恢复核对 {i:02}：核验任务状态、版本编号和有效片段数量并留存结果。" for i in range(1, 18)],
        ],
    ]
    for number, lines in enumerate(pages, 1):
        pdf.setFillColorRGB(0.08, 0.19, 0.23)
        pdf.setFont("STSong-Light", 21)
        pdf.drawString(46, 790, lines[0])
        pdf.setFont("STSong-Light", 11)
        for i, line in enumerate(lines[1:]):
            pdf.drawString(46, 746 - i * 23, line)
        pdf.setFont("STSong-Light", 9)
        pdf.drawString(46, 34, f"CiteWeave / ORIGINAL SYNTHETIC FIXTURE / {number:02}")
        pdf.showPage()
    pdf.save()
    print("Created original 2-page PDF fixture")
    import pypdfium2 as pdfium

    out = ROOT / ".artifacts/m1"
    out.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(target))
    for i, page in enumerate(document):
        page.render(scale=1).to_pil().save(out / f"fixture-{i}.png")


if __name__ == "__main__":
    main()
