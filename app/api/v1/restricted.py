"""One projection for the 「有，但你不能看」 tally - the only place it is built.

R200 之前这个形状被手写了两遍：``app/api/v1/chat.py`` 里一枚函数（两枚平铺文档出口共用），
``app/api/v1/data.py`` 的路由体里又一枚内联 dict。本模块把它们收成一处：键名与键序、
``reason_codes`` 的一次有序去重、两句人话的措辞与占位符都只在这里定义一次，出口只负责
递上被拒清单（``(资源标识, 稳定码)`` 的对）与本腿那一句模板常量。

口径的正典是 docs/api/contract-v1.md 的「restricted -> the one shared projection」那一节；
判定与计数永远在出口自己那一份分类结论里（文档腿 _classify_document_rows，数据腿
authorization_decision），本模块只负责解释，不再裁一次：只报数量与稳定码，不点名是哪一份
资源，也不把文件级拒绝改成 403。两句模板逐字搬自改前的两处（R186 / R201 各按字节钉着一句，
前端 DataPanel 抄着同一句），改一个字就是改契约。
"""
from __future__ import annotations

#: 数据文件腿那句话（逐字照抄 app/api/v1/data.py 改前的内联 f-string）。
DATA_FILE_TEMPLATE = "有 {count} 个数据文件存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文件的部门标注。"

#: 文档腿那句话（逐字照抄 app/api/v1/chat.py::_restricted_summary 改前的 f-string）。
DOCUMENT_TEMPLATE = "有 {count} 份文档存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文档的部门、密级标注。"


def restricted_summary(withheld: list[tuple[str, str]], template: str) -> dict:
    """Shape 「有，但你不能看」 into one field of a successful body.

    ``withheld`` 是 (资源标识, 稳定码) 的对，资源标识只进审计台账、一个字节都不进返回体；
    数与去重都从这一串现算，所以 ``count`` 与句子里的那个数是同一个 ``len(withheld)``。
    """
    return {
        "count": len(withheld),
        "reason_codes": list(dict.fromkeys(code for _name, code in withheld)),
        "message": template.format(count=len(withheld)),
    }
