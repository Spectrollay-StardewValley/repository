
#!/usr/bin/env python3
"""Generate light/dark GitHub repository statistics SVGs (stdlib only)."""

import json
import os
import re
import subprocess
import sys
import webbrowser
from html import escape
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = os.getenv('GITHUB_REPOSITORY', 'Spectrollay-StardewValley/Repository')
TOKEN = os.getenv('GITHUB_TOKEN', '')
API = 'https://api.github.com'
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'stats'
STATS_COMMIT = 'chore: update repository stats'


def request(path, params=None, allow_404=False):
    url = API + path + ('?' + urlencode(params) if params else '')
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'stardew-repository-stats',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if TOKEN:
        headers['Authorization'] = f'Bearer {TOKEN}'

    try:
        with urlopen(Request(url, headers=headers), timeout=25) as response:
            return json.load(response), response.headers
    except HTTPError as error:
        if allow_404 and error.code == 404:
            return None, None
        raise RuntimeError(f'GitHub API failed ({error.code}): {path}') from error


def local_git_log():
    """Count full HEAD history, excluding auto-generated stats commits."""
    try:
        shallow = subprocess.run(
            ['git', 'rev-parse', '--is-shallow-repository'],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        if shallow != 'false':
            return None

        result = subprocess.run(
            ['git', 'log', '--format=%s%x09%cI', 'HEAD'],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        rows = [
            line.split('\t', 1)
            for line in result.stdout.splitlines()
            if '\t' in line
        ]
        meaningful = [
            (subject, date)
            for subject, date in rows
            if subject != STATS_COMMIT
        ]
        last_date = meaningful[0][1][:10] if meaningful else None
        return len(meaningful), last_date
    except (OSError, subprocess.CalledProcessError):
        return None


def api_git_stats(branch):
    """Fallback when full local history is unavailable (includes stats commits)."""
    data, headers = request(
        f'/repos/{REPO}/commits',
        {'sha': branch, 'per_page': 1},
    )
    if not data:
        return 0, None

    match = re.search(
        r'[?&]page=(\d+)[^>]*>;\s*rel="last"',
        headers.get('Link', ''),
    )
    count = int(match.group(1)) if match else 1
    date = (data[0]['commit'].get('committer') or {}).get('date')
    return count, date[:10] if date else None


def issue_count(kind):
    data, _ = request(
        '/search/issues',
        {'q': f'repo:{REPO} is:{kind}', 'per_page': 1},
    )
    return data['total_count']


def format_size(kb):
    size = max(float(kb), 0.0)
    units = ('KB', 'MB', 'GB', 'TB')
    index = 0

    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    return f'{size:,.2f} {units[index]}'


def collect():
    repo, _ = request('/repos/' + REPO)
    release, _ = request('/repos/' + REPO + '/releases/latest', allow_404=True)
    commits, last_date = local_git_log() or api_git_stats(repo['default_branch'])

    return {
        'repository': REPO,
        'branch': repo['default_branch'],
        'stars': repo['stargazers_count'],
        'forks': repo['forks_count'],
        'commits': commits,
        'issues': issue_count('issue'),
        'prs': issue_count('pr'),
        'release': release['tag_name'] if release else 'No release',
        'size': format_size(repo['size']),
        'last_commit': last_date or 'N/A',
    }


def icon(kind, x, y, color, size=18):
    icons = {
        'star': {
            'mode': 'stroke',
            'stroke_width': 1.8,
            'body': '<path d="M12 3.2L14.63 8.53L20.5 9.38L16.25 13.52L17.25 19.35L12 16.6L6.75 19.35L7.75 13.52L3.5 9.38L9.37 8.53Z"/>',
        },
        'fork': {
            'mode': 'stroke',
            'stroke_width': 1.8,
            'body': (
                '<circle cx="6.5" cy="6" r="2.3"/>'
                '<circle cx="17.5" cy="6" r="2.3"/>'
                '<circle cx="6.5" cy="18" r="2.3"/>'
                '<path d="M6.5 8.3V15.7M15.2 6v4a2 2 0 0 1-2 2H9.5a3 3 0 0 0-3 3"/>'
            ),
        },
        'commit': {
            'mode': 'stroke',
            'stroke_width': 2,
            'body': (
                '<circle cx="12" cy="12" r="3"/>'
                '<line x1="2" x2="8.7" y1="12" y2="12"/>'
                '<line x1="15.3" x2="22" y1="12" y2="12"/>'
            ),
        },
        'issue': {
            'mode': 'stroke',
            'stroke_width': 1.9,
            'body': (
                '<circle cx="12" cy="12" r="7"/>'
                '<circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/>'
            ),
        },
        'pr': {
            'mode': 'stroke',
            'stroke_width': 2,
            'body': (
                '<circle cx="18" cy="18" r="3"/>'
                '<circle cx="6" cy="6" r="3"/>'
                '<path d="M13 6h3a2 2 0 0 1 2 2v7"/>'
                '<line x1="6" x2="6" y1="9" y2="21"/>'
            ),
        },
        'tag': {
            'mode': 'stroke',
            'stroke_width': 1.8,
            'body': (
                '<path d="M3 4.5A1.5 1.5 0 0 1 4.5 3H11l10 10-8 8-10-10Z"/>'
                '<circle cx="8" cy="8" r="2"/>'
            ),
        },
        'drive': {
            'mode': 'stroke',
            'stroke_width': 1.9,
            'body': (
                '<rect x="3.2" y="6.2" width="17.6" height="11.2" rx="2.2"/>'
                '<path d="M5.2 11.2h13.6"/>'
                '<circle cx="17.3" cy="14.4" r="1" fill="currentColor" stroke="none"/>'
            ),
        },
        'clock': {
            'mode': 'stroke',
            'stroke_width': 2,
            'body': (
                '<circle cx="12" cy="12" r="10"/>'
                '<polyline points="12 6 12 12 16.5 12"/>'
            ),
        },
        'scale': {
            'mode': 'stroke',
            'stroke_width': 1.8,
            'body': (
                '<path d="M12 2v19M5 7h14M7 7l-4 8h8L7 7ZM17 7l-4 8h8l-4-8Z"/>'
                '<path d="M8 21h8"/>'
            ),
        },
    }

    sizes = {
        'star': 19,
        'fork': 20,
        'commit': 20,
        'issue': 21,
        'pr': 18,
        'tag': 18,
        'drive': 20,
        'clock': 17,
        'scale': 15,
    }

    offsets = {
        'drive': (0, -0.5),
    }

    spec = icons[kind]
    display_size = sizes.get(kind, size)
    dx, dy = offsets.get(kind, (0, 0))

    x += (size - display_size) / 2 + dx
    y += (size - display_size) / 2 + dy

    if spec['mode'] == 'fill':
        return (
            f'<svg x="{x}" y="{y}" width="{display_size}" height="{display_size}" '
            f'viewBox="0 0 24 24" color="{color}" fill="currentColor">'
            f'{spec["body"]}</svg>'
        )

    return (
        f'<svg x="{x}" y="{y}" width="{display_size}" height="{display_size}" '
        f'viewBox="0 0 24 24" color="{color}" fill="none" '
        f'stroke="currentColor" stroke-width="{spec["stroke_width"]}" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'{spec["body"]}</svg>'
    )


def draw_svg(stats, dark=False):
    c = ({
        'bg': '#171C18',
        'panel': '#1D231F',
        'stroke': '#33443A',
        'text': '#EEF5EE',
        'muted': '#A7B8AD',
        'accent': '#9ED781',
        'badge': '#263427',
        'info': '#223126',
        'divider': '#3A4A3D',
    } if dark else {
        'bg': '#F7F8F4',
        'panel': '#FFFFFF',
        'stroke': '#CBD8C6',
        'text': '#314336',
        'muted': '#748474',
        'accent': '#3C8527',
        'badge': '#E1EEDB',
        'info': '#EDF4E9',
        'divider': '#D6E2D1',
    })

    font = 'Segoe UI, Arial, sans-serif'
    base = f'https://github.com/{stats["repository"]}'
    branch = stats.get('branch', 'main')
    links = {
        'star': f'{base}/stargazers',
        'fork': f'{base}/forks',
        'commit': f'{base}/commits/{branch}',
        'issue': f'{base}/issues?q=is%3Aissue',
        'pr': f'{base}/pulls?q=is%3Apr',
        'tag': f'{base}/releases',
        'drive': base,
        'clock': f'{base}/commits/{branch}',
        'scale': f'{base}/blob/{branch}/LICENSE',
    }

    def start_link(url):
        return f'<a href="{escape(url, quote=True)}" target="_blank" style="cursor: pointer">'

    items = [
        ('Stars', stats['stars'], 'star'),
        ('Forks', stats['forks'], 'fork'),
        ('Commits', stats['commits'], 'commit'),
        ('Issues', stats['issues'], 'issue'),
        ('Pull Requests', stats['prs'], 'pr'),
        ('Latest Release', stats['release'], 'tag'),
    ]

    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="780" height="452" viewBox="0 0 780 452" role="img" aria-label="Stardew Valley Repository statistics">
<rect width="780" height="452" rx="16" fill="{c['bg']}"/>
<rect x="1" y="1" width="778" height="450" rx="15" fill="none" stroke="{c['stroke']}"/>
<rect x="17" y="16" width="6" height="53" rx="3" fill="{c['accent']}"/>
{start_link(base)}
<text x="38" y="43" font-size="23" font-weight="700" fill="{c['text']}" font-family="{font}">Stardew Valley Repository</text>
<text x="38" y="64" font-size="12" fill="{c['muted']}" font-family="{font}">{escape(stats['repository'])}</text>
</a>
<rect x="640" y="27" width="122" height="26" rx="9" fill="{c['badge']}"/>
<text x="701" y="44" text-anchor="middle" font-size="10" font-weight="700" fill="{c['accent']}" font-family="{font}">REPOSITORY STATS</text>''']

    for i, (label, value, kind) in enumerate(items):
        x = 17 + (i % 3) * 252
        y = 85 + (i // 3) * 122
        value_text = escape(f'{value:,}' if isinstance(value, int) else str(value))
        font_size = 27 if len(value_text) <= 9 else 21 if len(value_text) <= 14 else 17

        parts.append(f'''{start_link(links[kind])}
<rect x="{x}" y="{y}" width="242" height="111" rx="11" fill="{c['panel']}" stroke="{c['stroke']}"/>
<text x="{x + 16}" y="{y + 29}" font-size="13" fill="{c['muted']}" font-family="{font}">{escape(label)}</text>
{icon(kind, x + 204, y + 16, c['accent'])}
<text x="{x + 16}" y="{y + 81}" font-size="{font_size}" font-weight="700" fill="{c['text']}" font-family="{font}">{value_text}</text>
</a>''')

    parts.append(f'''<rect x="17" y="343" width="746" height="63" rx="12" fill="{c['info']}"/>
<path d="M390 356v37" stroke="{c['divider']}" stroke-width="1"/>

{start_link(links['drive'])}
{icon('drive', 38, 367, c['accent'])}
<text x="64" y="381" font-size="14" fill="{c['muted']}" font-family="{font}">Repository Size</text>
<text x="175" y="381" font-size="17" font-weight="700" fill="{c['text']}" font-family="{font}">{escape(stats['size'])}</text>
</a>

{start_link(links['clock'])}
{icon('clock', 533, 367, c['accent'])}
<text x="560" y="381" font-size="14" fill="{c['muted']}" font-family="{font}">Last Commit</text>
<text x="743" y="381" text-anchor="end" font-size="16" font-weight="700" fill="{c['text']}" font-family="{font}">{escape(stats['last_commit'])}</text>
</a>

<text x="17" y="437" font-size="12" fill="{c['muted']}" font-family="{font}">Data from GitHub API</text>
{start_link(links['scale'])}
{icon('scale', 664, 424, c['accent'], 15)}
<text x="763" y="437" text-anchor="end" font-size="14" font-weight="700" fill="{c['accent']}" font-family="{font}">MIT License</text>
</a>
</svg>''')

    return '\n'.join(parts) + '\n'


def main():
    preview = '--preview' in sys.argv
    demo = preview or os.getenv('DEMO_STATS') == '1'

    if demo:
        stats = {
            'repository': REPO,
            'branch': 'main',
            'stars': 123,
            'forks': 45,
            'commits': 678,
            'issues': 12,
            'prs': 3,
            'release': 'v1.0.0',
            'size': '4.50 MB',
            'last_commit': '2026-10-11',
        }
        print('DEMO mode: illustrative numbers only')
    else:
        stats = collect()

    target = OUTPUT / 'preview' if preview else OUTPUT
    target.mkdir(parents=True, exist_ok=True)

    for theme in ('light', 'dark'):
        path = target / f'repository-stats-{theme}.svg'
        path.write_text(draw_svg(stats, theme == 'dark'), encoding='utf-8')
        print('Generated:', path)

        if preview:
            opened = webbrowser.open(path.resolve().as_uri())
            if not opened:
                print('Browser did not open automatically. Open this file manually:', path)


if __name__ == '__main__':
    main()
