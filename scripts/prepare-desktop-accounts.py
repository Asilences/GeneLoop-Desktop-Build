#!/usr/bin/env python3
"""Prepare a separate service plan for approved existing desktop accounts."""
import argparse
from pathlib import Path

from geneloop_service import load_plan, private_file, read, same_data, save


def prepare(plan_path, output, account_ids):
    plan = load_plan(plan_path)
    gateway = read(plan['gateway_config'])
    if not gateway.get('apiKey') or not gateway.get('memberPolicy', {}).get('control_token'):
        raise RuntimeError('Desktop model access requires the configured model and budget controller')
    if any(type(gateway.get(key)) is not int or not 1 <= gateway[key] <= 65535
           for key in ('upstreamControlPort', 'upstreamBrokerPort')):
        raise RuntimeError('Desktop model access requires configured budget controller and broker ports')
    accounts = read(private_file(Path(gateway['dataDir']) / 'accounts.json'))
    if accounts.get('version') != 1 or not isinstance(accounts.get('users'), list):
        raise RuntimeError('Desktop model access requires a valid existing account database')
    registered = {user['id'] for user in accounts['users'] if user.get('role') in ('owner', 'member')}
    if not account_ids or not set(account_ids) <= registered:
        raise RuntimeError('Desktop model access requires existing GeneLoop account IDs')
    current = gateway.get('desktopLocalModel') or {}
    gateway['desktopLocalModel'] = {**current,
        'accountIds': list(dict.fromkeys([*current.get('accountIds', []), *account_ids]))}

    old_gateway = plan['gateway_config']
    output = Path(output).absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    plan['gateway_config'] = str(output / 'gateway.json')
    plan['gateway']['argv'] = [
        plan['gateway_config'] if arg == old_gateway else arg for arg in plan['gateway']['argv']
    ]
    save(plan['gateway_config'], gateway)
    result = output / 'service.json'
    save(result, plan)
    same_data(load_plan(plan_path), load_plan(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--account-id', action='append', required=True)
    args = parser.parse_args()
    try:
        print(prepare(args.plan, args.output, args.account_id))
    except RuntimeError as error:
        parser.exit(1, str(error) + '\n')
    except (OSError, TypeError, ValueError, KeyError):
        parser.exit(1, 'Could not read or write the private desktop account plan.\n')
