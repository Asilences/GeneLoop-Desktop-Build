"""Frozen synthetic holdout for a second, context-windowed local PII scan."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import time

from src.adapters.rsi_chinese_privacy import ChineseTools
from src.adapters.rsi_privacy_candidates import candidate_context
from src.adapters.rsi_text_privacy import _scan, anonymize_text


CASES = (
    ('Paper', '保持 LaTeX。审稿稿件请寄到〔LOCATION|杭州市西湖区文二西路17号二单元503室〕，联系人〔PERSON|罗子琦〕。', '保持 LaTeX'),
    ('Paper', '按 APA 7 输出。通讯地址：〔LOCATION|武汉市江岸区，永清街26号附1栋1702〕。', '按 APA 7 输出'),
    ('Paper', '引用保留 DOI。作者通信请发给〔EMAIL|review-alpha@example.invalid〕。', '引用保留 DOI'),
    ('Paper', '两处结论给出 95% CI。编辑老师姓〔PERSON|司徒〕，全名〔PERSON|司徒清〕。', '95% CI'),
    ('Paper', '语言用中文。测试证件号是〔ID|000000199001011234〕，联系人〔PERSON|金叶岚〕。', '语言用中文'),
    ('Paper', '保留原始图表编号。线下寄送到〔LOCATION|锦川巷东头青荷苑5幢2门602〕。', '保留原始图表编号'),
    ('PPT', '用 16:9。客户说“送到〔LOCATION|深圳市南山区粤海街道，科苑路88号三栋B座1305〕”。', '用 16:9'),
    ('PPT', '英文副标题保留。联系手机：〔PHONE|+86 199 0000 0077〕，别写入演示稿。', '英文副标题保留'),
    ('PPT', '只做 12 页。联系微信〔SOCIAL|wxid_demo_alpha22〕，邮件〔EMAIL|slide-alpha@example.invalid〕。', '只做 12 页'),
    ('PPT', '每张图标注来源。快递填〔LOCATION|浦东新区银柳路5弄1号楼3单元9层901〕。', '每张图标注来源'),
    ('PPT', '图表保留 RMSE。收件人〔PERSON|柯念乔〕，QQ号〔SOCIAL|1234500678〕。', '图表保留 RMSE'),
    ('PPT', '生成 SVG 图例。杭州与深圳的城市名是标题里的公开研究地点。', '生成 SVG 图例'),
    ('Coding', '只改 test.py。登录账号：〔ACCOUNT|demo_operator_04〕；联系人〔PERSON|褚逸青〕。', '只改 test.py'),
    ('Coding', '保持 HTTP 204。测试收货地址〔LOCATION|青岛市崂山区海川路１２号２号楼６０８〕。', '保持 HTTP 204'),
    ('Coding', '不要改 JSON Schema。表单样例微信号：〔SOCIAL|coding_wx_demo05〕。', '不要改 JSON Schema'),
    ('Coding', '超时设为 120s。通知联系电话〔PHONE|198-0000-0672〕。', '超时设为 120s'),
    ('Coding', '保留 Python 3.12。验收账号是〔ACCOUNT|trial_ui_login_19〕，邮件是〔EMAIL|coding-demo@example.invalid〕。', '保留 Python 3.12'),
    ('Coding', '路径参数 id 固定为 12044。API 和 MCP 是接口名。', 'id 固定为 12044'),
    ('MCP', '表格保留 n = 24。老板住在〔LOCATION|北京市朝阳区北四环东路12号院 4 号楼 2 单元 804 室〕。', '表格保留 n = 24'),
    ('MCP', '对照取 3 轮。快递寄到〔LOCATION|古槐路江畔里2栋-1单元-1502〕。', '对照取 3 轮'),
    ('MCP', '只汇总结构字段。请发给联系人〔PERSON|卓越禾〕，QQ〔SOCIAL|1134500897〕。', '只汇总结构字段'),
    ('MCP', '按 24 fps 导出。住址：〔LOCATION|南昌市红谷滩区秋水路 6 号 4 栋 2 单元 1103 室〕。', '按 24 fps 导出'),
    ('MCP', '输出 Markdown 表格。联系地址在〔LOCATION|龙湖新区水杉街和荷塘路路口往东第三家〕。', '输出 Markdown 表格'),
    ('MCP', '保留 R² 和 AUC。第3单元是课程章节，2号楼是数据分组的公开标签。', '保留 R² 和 AUC'),
)
LABEL = re.compile(r'〔([A-Z]+)\|([^〕]+)〕')
CLAUSE = re.compile(r'[^。；;\r\n!?！？]+')
CUE = re.compile(r'寄|送到|住在|地址|联系人|收件人|电话|手机|QQ|微信|证件|账号|邮件')
MASK = '█'


def source(template):
    text, marks, offset = '', [], 0
    for item in LABEL.finditer(template):
        text += template[offset:item.start()]
        value = item[2]
        marks.append((item[1], len(text), len(text) + len(value)))
        text += value
        offset = item.end()
    return text + template[offset:], marks


def mask(text):
    result = anonymize_text(text, alias=lambda _, value: MASK * len(value))
    if len(result) != len(text):
        raise ValueError('unaligned_mask')
    return result


def guided(text, baseline):
    result = list(baseline)
    for clause in CLAUSE.finditer(text):
        value = clause[0]
        if len(value) > 160 or not CUE.search(value) or value == text:
            continue
        for index, char in enumerate(mask(value), clause.start()):
            if char == MASK:
                result[index] = MASK
    return ''.join(result)


def evaluate(backend):
    metrics = {key: {'covered': defaultdict(int), 'targets': defaultdict(int), 'preserved': 0,
                     'rejected': 0, 'gold_complement': 0, 'masked_gold_complement': 0, 'seconds': []}
               for key in ('single', 'repeat_masked', 'guided_original')}
    with candidate_context(backend):
        mask('中文姓名，账号。')
        for _, template, invariant in CASES:
            text, marks = source(template)
            gold = {i for _, start, end in marks for i in range(start, end)}
            for name, row in metrics.items():
                for label, _, _ in marks:
                    row['targets'][label] += 1
                started = time.perf_counter()
                try:
                    _scan(text)
                    result = mask(text)
                    if name == 'repeat_masked':
                        result = mask(result)
                    elif name == 'guided_original':
                        result = guided(text, result)
                    _scan(result)
                except Exception:
                    row['rejected'] += 1
                else:
                    row['preserved'] += invariant in result
                    row['masked_gold_complement'] += sum(c == MASK and i not in gold for i, c in enumerate(result))
                    row['gold_complement'] += len(text) - len(gold)
                    for label, start, end in marks:
                        row['covered'][label] += all(c == MASK for c in result[start:end])
                row['seconds'].append(time.perf_counter() - started)
    for row in metrics.values():
        elapsed = row.pop('seconds')
        row['median_ms'] = round(1000 * statistics.median(elapsed), 2)
        row['p95_ms'] = round(1000 * statistics.quantiles(elapsed, n=20, method='inclusive')[18], 2)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chinese-config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = args.chinese_config.read_bytes()
    results = {'fixture': 'independent_synthetic', 'cases': len(CASES), 'cloud_requests': 0,
               'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'chinese_config_sha256': hashlib.sha256(config).hexdigest(),
               'default': evaluate(None), 'chinese': evaluate(ChineseTools(json.loads(config)))}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(results, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
