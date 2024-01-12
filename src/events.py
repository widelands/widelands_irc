from colors import colorize
import subprocess
import requests
import re

def fmt_repo(data):
    repo = '[' + data['repository']['full_name'] + ']'
    return colorize(repo, 'royal', 'irc')

# Use git.io to get a shortened link for commit names, etc. which are too long
# https://git.io no longer available
def short_gh_link(link):
    conn = requests.post('https://git.io', data={'url':link})
    print('Header: {}'.format(conn.headers))
    return conn.headers['Location']

MAX_COMMIT_LOG_LEN = 5
MAX_COMMIT_LEN = 70

def fmt_commit(cmt):
    hsh = colorize(cmt['id'][:10], 'teal', 'irc')
    author = colorize(cmt['author']['name'], 'bold-green', 'irc')
    message = fmt_message(cmt['message'], MAX_COMMIT_LEN)

    return '{} {}: {}'.format(hsh, author, message)

def fmt_message(message, message_len=370):
    if message:
        message = message.replace('\r\n', ' ')
        message = message.replace('\n\n', ' ')
        message = message.replace('\n', '')
        if message.startswith('<!-- MIRRORED_BY_BUNNYBOT'):
            message = re.sub(r'<!-- MIRRORED_BY_BUNNYBOT.*?\* --- ', '', message)
        message = message[:message_len] \
            + ('..' if len(message) > message_len else '')

    return message

def fmt_last_commits(data):
    commits = list(map(fmt_commit, data['commits']))

    # make sure the commit list isn't too long
    if len(commits) <= MAX_COMMIT_LOG_LEN:
        return commits
    else:
        ellipsized_num = len(commits) - MAX_COMMIT_LOG_LEN + 1
        ellipsized = '{} more'.format(ellipsized_num)
        last_shown = MAX_COMMIT_LOG_LEN - 1

        last_line = '... and {} commit' \
            .format(colorize(ellipsized, 'royal', 'irc'))
        if ellipsized_num > 1: # add s to commitS
            last_line += 's'

        return commits[slice(0, last_shown)] + [last_line]

def handle_force_push(irc, data):
    author = colorize(data['pusher']['name'], 'bold', 'irc')

    before = colorize(data['before'][:10], 'bold-red', 'irc')
    after = colorize(data['after'][:10], 'bold-red', 'irc')

    branch = data['ref'].split('/')[-1]
    branch = colorize(branch, 'bold-blue', 'irc')

    irc.schedule_message("{} {} force-pushed {} from {} to {}:"
            .format(fmt_repo(data), author, branch, before, after))

    commits = fmt_last_commits(data)
    for commit in commits:
        irc.schedule_message(commit)

def handle_forward_push(irc, data):
    if 'name' in data['pusher'].keys():
        author = colorize(data['pusher']['name'], 'bold', 'irc')
    else:
        author = colorize(data['pusher']['username'], 'bold', 'irc')

    num_commits = len(data['commits'])
    num_commits = "{} commit{}".format(num_commits, 's' if num_commits > 1 else '')
    num_commits = colorize(num_commits, 'bold-teal', 'irc')

    branch = data['ref'].split('/')[-1]
    branch = colorize(branch, 'bold-blue', 'irc')

    irc.schedule_message("{} {} pushed {} to {}:"
            .format(fmt_repo(data), author, num_commits, branch))

    commits = fmt_last_commits(data)
    if commits:
        for commit in commits:
            irc.schedule_message(commit)
    else:
        message = fmt_message(data['head_commit']['message'])
        irc.schedule_message('{}'.format(message))

def handle_delete_branch(irc, data):
    author = colorize(data['pusher']['name'], 'bold', 'irc')
    action = colorize('deleted', 'red', 'irc')

    branch = data['ref'].split('/')[-1]
    branch = colorize(branch, 'bold-blue', 'irc')

    irc.schedule_message("{} {} {} {}"
            .format(fmt_repo(data), author, action, branch))

def handle_push_event(irc, data):
    if 'forced' and 'deleted' in data.keys():
        if data['forced']:
            handle_force_push(irc, data)
        elif data['deleted']:
            handle_delete_branch(irc, data)
        else:
            handle_forward_push(irc, data)
    else:
        handle_forward_push(irc, data)

def fmt_pr_action(action, merged):
    if action == 'opened' or action == 'reopened':
        action = colorize(action, 'green', 'irc')
    elif action == 'closed':
        if merged:
            action = colorize('merged', 'purple', 'irc')
        else:
            action = colorize(action, 'red', 'irc')
    else:
        action = colorize(action, 'brown', 'irc')

    return action

def handle_pull_request(irc, data):
    repo = fmt_repo(data)
    author = colorize(data['sender']['login'], 'bold', 'irc')
    action = fmt_pr_action(data['action'], data['pull_request']['merged'])
    pr_num = colorize('#{}'.format(data['number']), 'bold-blue', 'irc')
    title = data['pull_request']['title']
    message = fmt_message(data['pull_request']['body'])

    irc.schedule_message('{} {} {} pull request {}: {}'
            .format(repo, author, action, pr_num, title))
    if message:
        irc.schedule_message('{}'.format(message))

def handle_issue(irc, data):
    repo = fmt_repo(data)
    user = colorize(data['sender']['login'], 'bold', 'irc')

    action = data['action']
    if action in ['opened', 'closed']:
        action_color = 'red' if action == 'opened' else 'green'
    elif action == 'milestoned':
        action_color = 'red'
    else:
        irc.log_to_file('INFO', 'Action: {}'.format(action))
        print('Action: {}'.format(action))
        return
    action = colorize(action, action_color, 'irc')

    issue_num = colorize('#{}'.format(data['issue']['number']), 'bold-blue', 'irc')
    title = data['issue']['title']
    message = fmt_message(data['issue']['body'])

    irc.schedule_message('{} {} {} issue {}: {}'
            .format(repo, user, action, issue_num, title))
    #if action in ['opened', 'closed']:
    irc.schedule_message('{}'.format(message))

def handle_issue_comment(irc, data):
    repo = fmt_repo(data)
    title = fmt_message(data['issue']['title'], MAX_COMMIT_LEN)
    author = colorize(data['sender']['login'], 'bold', 'irc')
    issue_num = colorize('#{}'.format(data['issue']['number']), 'bold-blue', 'irc')
    message = fmt_message(data['comment']['body'])

    if data['action'] == 'created':
        irc.schedule_message('{} {} commented on issue {}: {}'
                .format(repo, author, issue_num, title))
    elif data['action'] == 'edited':
        action = colorize(data['action'], 'brown', 'irc')
        irc.schedule_message('{} {} {} a comment on issue {}: {}'
                .format(repo, author, action, issue_num, title))
    else:
        irc.schedule_message('{} {} do {} with issue {}: {}'
                .format(repo, author, data['action'], issue_num, title))
    irc.schedule_message('{}'.format(message))

def handle_status_event(irc, data):
    irc.log_to_file('INFO', 'Status: {}'.format(data['state']))
    print('Status: {}'.format(data['state']))
    if data['state'] == 'success':
        color = 'bold-green'
    elif data['state'] == 'error':
        color = 'red'
    elif data['state'] == 'failure':
        color = 'bold-red'
    elif data['state'] == 'pending':
        color = 'bold-teal'
    else:
        color = 'black'

    repo = fmt_repo(data)
    repo_name = data['repository']['full_name']
    after_id = data['sha'][:12]
    befor_id = data['commit']['parents'][0]['sha'][:12]
    commit_id = colorize(after_id, 'bold', 'irc')
    desc = colorize(data['description'], color, 'irc')
    target_url = data['target_url'].split('?', 1)[0]
    change = colorize('Change view:', 'teal', 'irc')
    build = colorize('Build details:', 'teal', 'irc')
    message = fmt_message(data['commit']['commit']['message'], MAX_COMMIT_LEN)
    commit_msg = colorize(message, 'green', 'irc')
    branch = colorize(data['branches'][0]['name'], 'bold-blue', 'irc')

    irc.schedule_message('{} {} on {}: {}'
            .format(repo, commit_id, branch, desc))
    irc.schedule_message('{} {}'
            .format(change, commit_msg))
    irc.schedule_message('{} {}'
            .format(build, target_url))

def handle_watch_event(irc, data):
    if data['action'] == 'started':
        message = colorize('has been starred by', 'bold-green', 'irc')
    else:
        irc.log_to_file('INFO', 'Watch event: {}'.format(data['action']))
        print('Watch event: {}'.format(data['action']))
    repo = fmt_repo(data)
    sender = data['sender']['login']
    irc.schedule_message('{} {} {}'.format(repo, message, sender))

def handle_check_run(irc, data):
    if data['action'] != "created":
        repo = fmt_repo(data)
        check_suite_id = colorize('{}'.format(data['check_run']['check_suite']['id']), 'bold-white', 'irc')
        color_check_status = "green" if data['check_run']['conclusion'] == "success" else "red"
        check_status = colorize(data['check_run']['conclusion'], color_check_status, 'irc')
        irc.schedule_message('{} Check ID {}: {} {} {}: {}/{}'.format(
            repo
            , check_suite_id
            , data['check_run']['name']
            , colorize('for', 'bold-white', 'irc')
            , data['check_run']['check_suite']['head_branch']
            , colorize(data['check_run']['status'], 'lime', 'irc')
            , check_status
            ))

def handle_check_suite(irc, data):
    repo = fmt_repo(data)
    suite_id = colorize('{}'.format(data['check_suite']['id']), 'bold-white', 'irc')
    color_suite_status = "green" if data['check_suite']['conclusion'] == "success" else "red"
    suite_status = colorize(data['check_suite']['conclusion'], color_suite_status, 'irc')
    suite_check = "checks" if data['check_suite']['latest_check_runs_count'] > 1 else "check"
    suite_checks = '{} {}'.format(data['check_suite']['latest_check_runs_count'], suite_check)
    irc.schedule_message('{} Suite ID {}: {} {} {}/{}'.format(
        repo
        , suite_id
        , data['check_suite']['head_branch']
        , suite_checks
        , colorize(data['check_suite']['status'], 'lime', 'irc')
        , suite_status
        ))

def handle_ping_event(irc, data):
    pass

def handle_release(irc, data):
    pass

def handle_pull_request_comment(irc, data):
    pass

def handle_pull_request_review(irc, data):
    pass

def handle_pull_request_review_comment(irc, data):
    pass

def handle_create(irc, data):
    pass

def handle_delete(irc, data):
    pass

def handle_event(irc, event, data):
    msg = ''
    irc.log_to_file('INFO', event)
    if event == 'ping':
        handle_ping_event(irc, data)
    elif event == 'push':
        handle_push_event(irc, data)
    elif event == 'pull_request':
        handle_pull_request(irc, data)
    elif event == 'pull_request_comment':
        handle_pull_request_comment(irc, data)
    elif event == 'issues':
        handle_issue(irc, data)
    elif event == 'issue_comment':
        handle_issue_comment(irc, data)
    elif event == 'status':
        handle_status_event(irc, data)
    elif event == 'watch':
        handle_watch_event(irc, data)
    elif event == 'check_run':
        handle_check_run(irc, data)
    elif event == 'release':
        handle_release(irc, data)
    elif event == 'check_suite':
        handle_check_suite(irc, data)
    elif event == 'pull_request_review':
        handle_pull_request_review(irc, data)
    elif event == 'pull_request_review_comment':
        handle_pull_request_review_comment(irc, data)
    elif event == 'create':
        handle_create(irc, data)
    elif event== 'delete':
        handle_delete(irc, data)
    else:
        msg = 'Unknown event type: {}'.format(event)
    msg = 'handle_event: {}'.format(event) if not msg else msg
    irc.log_to_file('INFO', msg)
    irc.log_to_file('DEBUG', data)
    print(msg)

