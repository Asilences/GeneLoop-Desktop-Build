#!/usr/bin/env python3
"""Preserve certified Paper/PPT IR after explicitly reusable member invitations.

Preview is the default. Only the reviewed gateway source lock may differ.
--write creates fresh releases; --update-registry explicitly selects them.
No learned programs, MCP schemas, evidence, permissions or model policy change.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'shared_invite_compat', ROOT / 'scripts/reexport-native-capabilities-compat.py')
compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compat)
compat.RELEASES = [
    ('paper-web-v44', 'paper-web-v45', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json', {'scripts/harless_gateway.mjs'}),
    ('ppt-master-v41', 'ppt-master-v42', 'ppt',
     'scenarios/ppt_master/contracts.json', {'scripts/harless_gateway.mjs'}),
]
compat.REGISTRY_SELECTED = {old: old for old, *_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-shared-invite-compat.py'}
_original_record = compat.compatibility_record
_original_prepare = compat.prepare


def compatibility_record(candidate, validation_record):
    value = _original_record(candidate, validation_record)
    value.update(
        repairs=['explicit_reusable_member_invitation_with_owner_authorized_rotation',
                 'concurrent_registration_rechecks_invitation_after_password_hashing'],
        runtime_delta='The account gateway supports one permanent reusable member invitation. '
                      'The existing owner-password and loopback-admin checks authorize creation/rotation; '
                      'rotation revokes the previous shared code without changing existing users. '
                      'Single-use invitations, member roles, account isolation, model/task/tool authority '
                      'and learned IR remain unchanged.',
        model_task_authority_changed=False,
    )
    return value


def prepare(candidate, directory, validation_record):
    _original_prepare(candidate, directory, validation_record)
    # README is informational, outside the certified executable file set.
    (directory / 'README.md').write_text(
        '# ' + candidate['release'] + '\n\n'
        '基于 ' + candidate['previous'] + ' 的共享邀请码网关兼容版本。'
        '只更新已审阅的网关源码锁，并绑定本轮兼容脚本。\n\n'
        '新增明确的永久共享成员邀请码及管理员换码；注册仍使用原角色和账号隔离，'
        '旧单次码保留。MCP、任务/模型权限、Motif 匹配与执行规则均未修改。\n\n'
        'library、online manifest、task、tool schemas、source evidence 五项逐字节保留；'
        '旧库未覆盖。零新增训练任务、零模型调用，不代表质量或费用效果晋级。\n\n'
        '验证记录：' + validation_record + '。\n', encoding='utf-8')


compat.compatibility_record = compatibility_record
compat.prepare = prepare
if __name__ == '__main__':
    compat.main()
