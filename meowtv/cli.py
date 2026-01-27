"""MeowTV CLI - Main command-line interface."""

import asyncio
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table
from rich.text import Text
from rich import print as rprint

from meowtv import __version__
from meowtv.config import get_config, save_config, Config
from meowtv.models import ContentItem, MovieDetails, Episode
from meowtv.favorites import get_favorites_manager
from meowtv.player import play, get_available_players, is_player_available
from meowtv.downloader import download, is_download_available

console = Console()


# ===== PROVIDER HELPERS =====

def get_provider_instance(name: str):
    """Get a provider instance by name."""
    from meowtv.providers import get_provider
    return get_provider(name)


def get_all_provider_names() -> list[str]:
    """Get all available provider names."""
    return ["meowverse", "meowtv", "meowtoon"]


# ===== UPDATE CHECKER =====

_update_checked = False  # Only check once per session

def check_for_updates():
    """Check PyPI for new version and display update message if available."""
    global _update_checked
    if _update_checked:
        return
    _update_checked = True
    
    try:
        import urllib.request
        import json
        
        # Quick timeout to avoid blocking
        req = urllib.request.Request(
            "https://pypi.org/pypi/meowtv/json",
            headers={"User-Agent": "MeowTV-CLI"}
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            latest = data.get("info", {}).get("version", "")
            
            if latest and latest != __version__:
                # Compare versions (simple string comparison works for semver)
                from packaging import version
                try:
                    if version.parse(latest) > version.parse(__version__):
                        console.print(f"\n[yellow]⬆ Update available:[/] [bold]{__version__}[/] → [bold green]{latest}[/]")
                        console.print(f"[dim]  Run: pip install --upgrade meowtv[/]\n")
                except:
                    # Fallback: simple string compare
                    if latest > __version__:
                        console.print(f"\n[yellow]⬆ Update available:[/] [bold]{__version__}[/] → [bold green]{latest}[/]")
                        console.print(f"[dim]  Run: pip install --upgrade meowtv[/]\n")
    except:
        # Silently fail - don't block user
        pass


# ===== DISPLAY HELPERS =====

def display_banner():
    """Display the MeowTV banner."""
    banner = """
    ╔╦╗┌─┐┌─┐┬ ┬╔╦╗╦  ╦
    ║║║├┤ │ ││││ ║ ╚╗╔╝
    ╩ ╩└─┘└─┘└┴┘ ╩  ╚╝ 
    """
    console.print(Panel(
        Text(banner, style="bold cyan"),
        title="[bold white]🐱 MeowTV CLI[/]",
        subtitle=f"v{__version__}"
    ))


def display_content_table(items: list[ContentItem], title: str = "Results"):
    """Display a table of content items."""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Type", style="green", width=8)
    table.add_column("ID", style="dim", width=20)
    
    for i, item in enumerate(items, 1):
        table.add_row(
            str(i),
            item.title or "(No title)",
            item.type,
            item.id[:20] if len(item.id) > 20 else item.id
        )
    
    console.print(table)


def display_details(details: MovieDetails):
    """Display content details."""
    # Header
    console.print(Panel(
        f"[bold cyan]{details.title}[/]",
        subtitle=f"[dim]{details.year or 'N/A'}[/] • [yellow]★ {details.score or 'N/A'}[/]"
    ))
    
    # Description
    if details.description:
        console.print(f"\n[dim]{details.description[:300]}{'...' if len(details.description) > 300 else ''}[/]\n")
    
    # Episodes table
    if details.episodes:
        table = Table(title=f"Episodes ({len(details.episodes)})", show_header=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("S", style="magenta", width=3)
        table.add_column("E", style="green", width=3)
        table.add_column("Title", style="cyan")
        
        for i, ep in enumerate(details.episodes[:50], 1):  # Limit display
            table.add_row(
                str(i),
                str(ep.season),
                str(ep.number),
                ep.title or f"Episode {ep.number}"
            )
        
        if len(details.episodes) > 50:
            console.print(f"[dim](Showing first 50 of {len(details.episodes)} episodes)[/]")
        
        console.print(table)


def display_favorites():
    """Display favorites list."""
    manager = get_favorites_manager()
    favorites = manager.list_all()
    
    if not favorites:
        console.print("[yellow]No favorites yet. Add some with 'meowtv favorites add <id>'[/]")
        return
    
    table = Table(title=f"Favorites ({len(favorites)})", show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Type", style="green", width=8)
    table.add_column("Provider", style="magenta", width=12)
    table.add_column("Added", style="dim", width=12)
    
    for i, fav in enumerate(favorites, 1):
        added = fav.added_at[:10] if fav.added_at else "N/A"
        table.add_row(str(i), fav.title, fav.type, fav.provider, added)
    
    console.print(table)


# ===== ASYNC RUNNERS =====

def run_async(coro):
    """Run an async function."""
    return asyncio.run(coro)


# ===== CLI COMMANDS =====

from meowtv.providers.proxy import set_proxy_url

@click.group(invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="Show version")
@click.pass_context
def main(ctx, version):
    """MeowTV CLI - Stream content from your terminal."""
    if version:
        console.print(f"MeowTV CLI v{__version__}")
        return
    
    # Initialize proxy from config
    config = get_config()
    set_proxy_url(config.proxy_url)
    
    # Check for updates (runs once per session)
    check_for_updates()
    
    if ctx.invoked_subcommand is None:
        # Interactive mode
        interactive_mode()







def select_content_interactively(provider_name: str, query: str = None, allow_season_download: bool = False) -> tuple[Optional[ContentItem], Optional[str], Optional[str], Optional[str]]:
    """
    Interactively search and select content/episode.
    Returns: (content_item, source_id, episode_id, episode_title)
    If allow_season_download is True, episode_id can be "ALL_S{season_num}"
    """
    import questionary
    
    config = get_config()
    prov_name = provider_name or config.default_provider
    prov = get_provider_instance(prov_name)
    
    if not prov:
        console.print(f"[red]Provider '{prov_name}' not found[/]")
        return None, None, None, None
    
    # 1. Search
    if not query:
        query = Prompt.ask("Search query")
    
    console.print(f"[dim]Searching {prov.name} for '{query}'...[/]")
    results = run_async(prov.search(query))
    
    if not results:
        console.print("[yellow]No results found[/]")
        return None, None, None, None
    
    # 2. Select Content
    choices = [
        questionary.Choice(
            title=f"{item.title} [{item.type}]",
            value=item
        )
        for item in results[:20]
    ]
    choices.append(questionary.Choice(title="[Cancel]", value=None))
    
    selected = questionary.select(
        "Select content (↑↓ arrows):",
        choices=choices,
    ).ask()
    
    if not selected:
        return None, None, None, None
    
    console.print(f"\n[dim]Loading {selected.title}...[/]")
    details = run_async(prov.fetch_details(selected.id))
    
    if not details:
        console.print("[red]Failed to load details[/]")
        return None, None, None, None
    
    # 3. Select Episode (if applicable)
    ep_id = None
    source_id = selected.id  # Default to main ID
    ep_title = details.title
    
    if details.episodes and len(details.episodes) > 1:
        # Group by season
        seasons = {}
        for ep in details.episodes:
            s = ep.season
            if s not in seasons:
                seasons[s] = []
            seasons[s].append(ep)
        
        # Select Season
        if len(seasons) > 1:
            season_choices = [
                questionary.Choice(title=f"Season {s} ({len(eps)} eps)", value=s)
                for s, eps in sorted(seasons.items())
            ]
            season_choices.append(questionary.Choice(title="[Cancel]", value=None))
            
            selected_season = questionary.select("Select season:", choices=season_choices).ask()
            if not selected_season:
                return None, None, None, None
            season_episodes = seasons[selected_season]
        else:
            selected_season = list(seasons.keys())[0] if seasons else 1
            season_episodes = details.episodes
        
        # Select Episode
        ep_choices = []
        
        # Add "Download Whole Season" option if enabled
        if allow_season_download:
             ep_choices.append(questionary.Choice(
                title=f"📥 Download Whole Season {selected_season} ({len(season_episodes)} eps)",
                value=f"ALL_S{selected_season}"
            ))

        ep_choices.extend([
            questionary.Choice(
                title=f"S{ep.season}E{ep.number}: {ep.title or f'Episode {ep.number}'}",
                value=ep
            )
            for ep in season_episodes
        ])
        ep_choices.append(questionary.Choice(title="[Cancel]", value=None))
        
        selected_ep = questionary.select("Select episode:", choices=ep_choices).ask()
        if not selected_ep:
            return None, None, None, None
        
        if isinstance(selected_ep, str) and selected_ep.startswith("ALL_s"): # Handle lowercase too just in case
             ep_id = selected_ep
             ep_title = f"Season {selected_season}"
        elif isinstance(selected_ep, str) and selected_ep.startswith("ALL_S"):
             ep_id = selected_ep
             ep_title = f"Season {selected_season}"
        else:
            ep_id = selected_ep.id
            source_id = selected_ep.source_movie_id or selected.id
            ep_title = f"{details.title} - {selected_ep.title or f'S{selected_ep.season}E{selected_ep.number}'}"
    
    elif details.episodes:
        # Movie / Single episode
        ep_id = details.episodes[0].id
        source_id = details.episodes[0].source_movie_id or selected.id
    
    return selected, source_id, ep_id, ep_title


@main.command()
@click.argument("query")
@click.option("--provider", "-p", default=None, help="Provider to search (meowverse, meowtv, meowtoon)")
@click.option("--interactive", "-i", is_flag=True, default=True, help="Enable interactive selection")
def search(query: str, provider: Optional[str], interactive: bool):
    """Search for content and optionally select to play."""
    import questionary
    
    config = get_config()
    provider_name = provider or config.default_provider
    
    prov = get_provider_instance(provider_name)
    if not prov:
        console.print(f"[red]Provider '{provider_name}' not found[/]")
        return
    
    console.print(f"[dim]Searching {prov.name} for '{query}'...[/]")
    
    async def do_search():
        return await prov.search(query)
    
    results = run_async(do_search())
    
    if not results:
        console.print("[yellow]No results found[/]")
        return
    
    # Show results table
    # Show results table
    # display_content_table(results, f"Search Results - {prov.name}")
    
    if interactive:
        # Build choices for selection
        choices = [
            questionary.Choice(
                title=f"{item.title} [{item.type}]",
                value=item
            )
            for item in results[:20]  # Limit to 20 for usability
        ]
        choices.append(questionary.Choice(title="[Cancel]", value=None))
        
        # Let user select with arrow keys
        selected = questionary.select(
            "Select content to play (↑↓ arrows, Enter to select):",
            choices=choices,
        ).ask()
        
        if not selected or not hasattr(selected, 'id'):
            return
        
        console.print(f"\n[dim]Loading {selected.title}...[/]")
        
        # Fetch details first
        async def get_details():
            return await prov.fetch_details(selected.id)
        
        details = run_async(get_details())
        
        if not details:
            console.print("[red]Failed to load details[/]")
            return
        
        # If it's a series with episodes, let user select
        ep_id = None
        if details.episodes and len(details.episodes) > 1:
            # Group episodes by season
            seasons = {}
            for ep in details.episodes:
                s = ep.season
                if s not in seasons:
                    seasons[s] = []
                seasons[s].append(ep)
            
            # If multiple seasons, let user select season first
            if len(seasons) > 1:
                season_choices = [
                    questionary.Choice(
                        title=f"Season {s} ({len(eps)} episodes)",
                        value=s
                    )
                    for s, eps in sorted(seasons.items())
                ]
                season_choices.append(questionary.Choice(title="[Cancel]", value=None))
                
                selected_season = questionary.select(
                    "Select season:",
                    choices=season_choices,
                ).ask()
                
                if not selected_season:
                    return
                
                season_episodes = seasons[selected_season]
            else:
                # Single season
                season_episodes = details.episodes
            
            # Let user select episode
            ep_choices = [
                questionary.Choice(
                    title=f"S{ep.season}E{ep.number}: {ep.title or f'Episode {ep.number}'}",
                    value=ep
                )
                for ep in season_episodes
            ]
            ep_choices.append(questionary.Choice(title="[Cancel]", value=None))
            
            selected_ep = questionary.select(
                "Select episode:",
                choices=ep_choices,
            ).ask()
            
            if not selected_ep:
                return
            
            ep_id = selected_ep.id
            ep_title = f"{details.title} - {selected_ep.title or f'S{selected_ep.season}E{selected_ep.number}'}"
        elif details.episodes:
            # Single episode (movie)
            ep_id = details.episodes[0].id
            ep_title = details.title
        else:
            console.print("[red]No episodes found[/]")
            return
        
        # Fetch stream
        console.print(f"[dim]Loading stream...[/]")
        
        # Fetch stream
        console.print(f"[dim]Loading stream...[/]")
        
        async def get_stream():
            # Resolving source_id locally for duplicates search logic
            # We need to find the episode in details to get source_movie_id if we didn't use the helper
            # But here we have 'details' variable available from earlier in this scope!
            source_id = selected.id
            if ep_id and details.episodes:
                 target_ep = next((e for e in details.episodes if e.id == ep_id), None)
                 if target_ep and target_ep.source_movie_id:
                     source_id = target_ep.source_movie_id
            
            return await prov.fetch_stream(source_id, ep_id)
        
        stream = run_async(get_stream())
        
        if stream:
            console.print(f"[green]▶ Playing: {ep_title}[/]")
            run_async(play(stream, title=ep_title, suppress_output=("meowverse" not in prov.name.lower())))
        else:
            console.print("[red]Failed to get stream[/]")
    else:
        console.print(f"\n[dim]Use 'meowtv play <id>' to play[/]")


@main.command()
@click.argument("query_or_id", required=False)
@click.option("--provider", "-p", default=None, help="Provider name")
def details(query_or_id: Optional[str], provider: Optional[str]):
    """Show content details (ID or search query)."""
    config = get_config()
    provider_name = provider or config.default_provider
    
    # Resolve content_id from query if needed
    content_id = None
    
    if not query_or_id:
        # No arg -> interactive search
        selected, _, _, _ = select_content_interactively(provider_name)
        if not selected:
            return
        content_id = selected.id
    elif query_or_id.isdigit():
        # Direct ID
        content_id = query_or_id
    else:
        # Search query -> interactive
        selected, _, _, _ = select_content_interactively(provider_name, query=query_or_id)
        if not selected:
            return
        content_id = selected.id
    
    prov = get_provider_instance(provider_name)
    if not prov:
        console.print(f"[red]Provider '{provider_name}' not found[/]")
        return
    
    console.print(f"[dim]Fetching details from {prov.name}...[/]")
    
    async def do_fetch():
        return await prov.fetch_details(content_id)
    
    result = run_async(do_fetch())
    
    if not result:
        console.print("[red]Content not found[/]")
        return
    
    display_details(result)


@main.command("play")
@click.argument("query_or_id", required=False)
@click.option("--episode", "-e", default=None, help="Episode ID (for series)")
@click.option("--provider", "-p", default=None, help="Provider name")
@click.option("--player", type=click.Choice(["mpv", "vlc"]), default=None, help="Player to use")
@click.option("--quality", "-q", default=None, help="Quality (1080p, 720p, 480p)")
def play_cmd(query_or_id: Optional[str], episode: Optional[str], provider: Optional[str], player: Optional[str], quality: Optional[str]):
    """Play content (ID or search query)."""
    config = get_config()
    provider_name = provider or config.default_provider
    player = player or config.default_player
    
    # Resolve content
    content_id = None
    ep_id = episode
    title = "MeowTV Stream"
    
    if not query_or_id:
        # No arg -> interactive search
        selected, source_id, sel_ep_id, sel_title = select_content_interactively(provider_name)
        if not selected:
            return
        content_id = source_id or selected.id
        ep_id = sel_ep_id
        title = sel_title
    elif query_or_id.isdigit():
        # Direct ID
        content_id = query_or_id
    else:
        # Search query -> interactive
        selected, source_id, sel_ep_id, sel_title = select_content_interactively(provider_name, query=query_or_id)
        if not selected:
            return
        content_id = source_id or selected.id
        ep_id = sel_ep_id
        title = sel_title
    
    prov = get_provider_instance(provider_name)
    if not prov:
        console.print(f"[red]Provider '{provider_name}' not found[/]")
        return
    
    if not is_player_available(player):
        console.print(f"[red]{player} not found. Available: {get_available_players()}[/]")
        return
    
    async def do_play():
        nonlocal ep_id, title, content_id
        
        # If direct ID without interactive selection, fetch details
        # If direct ID without interactive selection, fetch details
        if query_or_id and query_or_id.isdigit():
            details = await prov.fetch_details(content_id)
            if not details:
                return None, None
            title = details.title
            if not ep_id and details.episodes:
                # Default to first episode
                ep = details.episodes[0]
                ep_id = ep.id
                # Fix for MeowTV: update content_id if source_movie_id differs
                if ep.source_movie_id and ep.source_movie_id != content_id:
                    # We can't easily change content_id here as it's captured in closure?
                    # Actually we can if we make it nonlocal or just return it?
                    # Simpler: just use it for the fetch_stream call below
                    pass 

            # If we have an ep_id (either provided or defaulted), we must ensure we use the correct source_movie_id
            if ep_id and details.episodes:
                # Find the episode object
                target_ep = next((e for e in details.episodes if e.id == ep_id), None)
                if target_ep and target_ep.source_movie_id:
                     # Update content_id for the stream fetch
                     content_id = target_ep.source_movie_id

        if not ep_id:
            console.print("[red]No episode ID found[/]")
            return None, None
        
        # Get stream
        stream = await prov.fetch_stream(content_id, ep_id)
        return title, stream
    
    console.print(f"[dim]Loading stream from {prov.name}...[/]")
    result_title, stream = run_async(do_play())
    
    if not stream:
        console.print("[red]Failed to get stream URL[/]")
        return
    
    console.print(f"[green]▶ Playing: {result_title}[/]")
    console.print(f"[dim]Player: {player} | Quality: {quality or 'auto'}[/]")
    
    process = run_async(play(stream, player=player, title=result_title, quality=quality, suppress_output=("meowverse" not in prov.name.lower())))
    
    if process:
        pass


@main.command("download")
@click.argument("query_or_id", required=False)
@click.option("--episode", "-e", default=None, help="Episode ID (for series)")
@click.option("--season", "-s", type=int, default=None, help="Season number to download entirely")
@click.option("--provider", "-p", default=None, help="Provider name")
@click.option("--output", "-o", default=None, help="Output directory")
@click.option("--quality", "-q", default=None, help="Quality (1080p, 720p, 480p)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation for batch downloads")
def download_cmd(query_or_id: Optional[str], episode: Optional[str], season: Optional[int], provider: Optional[str], output: Optional[str], quality: Optional[str], yes: bool):
    """Download content (ID or Query)."""
    if not is_download_available():
        console.print("[red]Neither yt-dlp nor ffmpeg found. Install one to enable downloads.[/]")
        return
    
    config = get_config()
    provider_name = provider or config.default_provider
    
    # Resolve content
    content_id = None
    ep_id = episode
    title = "Download"
    is_interactive = False
    
    # Case 1: No arg provided -> Interactive Search
    if not query_or_id:
        selected, source_id, sel_ep_id, sel_ep_title = select_content_interactively(provider_name, allow_season_download=True)
        if not selected:
            return
        content_id = source_id or selected.id
        ep_id = sel_ep_id
        title = sel_ep_title
        is_interactive = True
        
    # Case 2: ID provided (digits)
    elif query_or_id.isdigit():
        content_id = query_or_id
        
    # Case 3: Query provided -> Interactive Search
    else:
        selected, source_id, sel_ep_id, sel_ep_title = select_content_interactively(provider_name, query=query_or_id, allow_season_download=True)
        if not selected:
            return
        content_id = source_id or selected.id
        ep_id = sel_ep_id
        title = sel_ep_title
        is_interactive = True

    prov = get_provider_instance(provider_name)
    if not prov:
        console.print(f"[red]Provider '{provider_name}' not found[/]")
        return

    # --- Batch Download Logic ---
    target_season = season
    
    # Check if interactive selected "ALL_S{x}"
    if ep_id and isinstance(ep_id, str) and ep_id.startswith("ALL_S"):
        try:
            target_season = int(ep_id.replace("ALL_S", ""))
            ep_id = None # Clear ep_id so we trigger batch logic
        except: pass
        
    if target_season is not None:
        # Fetch details to get all episodes for season
        console.print(f"[dim]Fetching season {target_season} details...[/]")
        details = run_async(prov.fetch_details(content_id))
        
        if not details:
            console.print("[red]Content not found[/]")
            return
            
        # Filter episodes by season
        season_eps = [ep for ep in details.episodes if ep.season == target_season]
        
        if not season_eps:
             console.print(f"[red]No episodes found for Season {target_season}[/]")
             return
             
        console.print(f"[cyan]Found {len(season_eps)} episodes in Season {target_season}[/]")
        
        if not yes and not is_interactive: # If interactive, user explicitly chose "Download Whole Season"
             if not click.confirm(f"Download all {len(season_eps)} episodes?"):
                 return

        # Prepare directory: Output > Show Name > Season X
        base_output = output or config.download_dir
        
        # Clean show title
        safe_show = "".join(c for c in details.title if c.isalnum() or c in " -_").strip()[:50]
        season_dir = Path(base_output) / safe_show / f"Season {target_season}"
        
        console.print(f"[dim]Downloading to: {season_dir}[/]")
        
        success_count = 0
        for i, ep in enumerate(season_eps, 1):
             ep_title = f"{details.title} - {ep.title or f'S{ep.season}E{ep.number}'}"
             console.print(f"\n[bold]({i}/{len(season_eps)}) {ep_title}[/]")
             
             try:
                 # Fetch stream
                 # Use source_movie_id for the episode if available
                 ep_source_id = ep.source_movie_id or content_id
                 stream = run_async(prov.fetch_stream(ep_source_id, ep.id))
                 if stream:
                     dl_res = download(stream, ep_title, output_dir=season_dir, quality=quality)
                     if dl_res:
                         console.print(f"[green]✓ Done[/]")
                         success_count += 1
                     else:
                         console.print("[red]Failed[/]")
                 else:
                     console.print("[red]No stream[/]")
             except Exception as e:
                 console.print(f"[red]Error: {e}[/]")
                 
        console.print(f"\n[green]Batch download finished: {success_count}/{len(season_eps)} successful[/]")
        return
        
    # --- Single Episode Logic (Existing) ---

    async def do_fetch():
        # If we selected interactively, we have ep_id.
        # If direct ID, we might need to fetch details to get default ep_id.
        
        if not ep_id:
            details = await prov.fetch_details(content_id)
            if not details:
                console.print("[red]Content not found[/]")
                return None, None
            
            # Default to first episode
            target_ep_id = details.episodes[0].id if details.episodes else None
            if not target_ep_id:
                return details, None
             
            final_ep_id = target_ep_id
            final_title = f"{details.title} - {details.episodes[0].title}"
            
            # Auto-create directory for single file too?
            # User request: "change directory of download" -> implied structure?
            # Let's add partial structure: Show Name/Season X/
            s_num = details.episodes[0].season
            return final_title, await prov.fetch_stream(content_id, final_ep_id), details.title, s_num
        else:
            final_ep_id = ep_id
            final_title = title 
            # We don't verify season here easily without details, stick to standard
            return final_title, await prov.fetch_stream(content_id, final_ep_id), None, None

    console.print(f"[dim]Preparing download from {prov.name}...[/]")
    result = run_async(do_fetch())
    
    if not result:
         return
         
    if len(result) == 4:
         result_title, stream, show_title, s_num = result
    else:
         result_title, stream = result[:2]
         show_title, s_num = None, None
    
    if not stream:
        console.print("[red]Failed to get stream URL[/]")
        return
    
    # Enhanced Directory for Single Episodes as well
    final_output = output
    if not final_output and show_title and s_num:
         config = get_config()
         base = config.download_dir
         safe_show = "".join(c for c in show_title if c.isalnum() or c in " -_").strip()[:50]
         final_output = Path(base) / safe_show / f"Season {s_num}"

    dl_res = download(stream, result_title, output_dir=final_output, quality=quality)
    
    if dl_res:
        console.print(f"[green]✓ Downloaded: {dl_res}[/]")
    else:
        console.print("[red]Download failed[/]")



@main.group()
def favorites():
    """Manage favorites."""
    pass


@favorites.command("list")
def favorites_list():
    """List all favorites."""
    display_favorites()


@favorites.command("add")
@click.argument("query_or_id", required=False)
@click.option("--provider", "-p", default=None, help="Provider name")
def favorites_add(query_or_id: Optional[str], provider: Optional[str]):
    """Add content to favorites (ID or search query)."""
    config = get_config()
    provider_name = provider or config.default_provider
    
    # Resolve content_id
    content_id = None
    
    if not query_or_id:
        # No arg -> interactive search
        selected, _, _ = select_content_interactively(provider_name)
        if not selected:
            return
        content_id = selected.id
    elif query_or_id.isdigit():
        # Direct ID
        content_id = query_or_id
    else:
        # Search query -> interactive
        selected, _, _ = select_content_interactively(provider_name, query=query_or_id)
        if not selected:
            return
        content_id = selected.id
    
    prov = get_provider_instance(provider_name)
    if not prov:
        console.print(f"[red]Provider '{provider_name}' not found[/]")
        return
    
    async def do_fetch():
        return await prov.fetch_details(content_id, include_episodes=False)
    
    console.print(f"[dim]Fetching details...[/]")
    details = run_async(do_fetch())
    
    if not details:
        console.print("[red]Content not found[/]")
        return
    
    manager = get_favorites_manager()
    fav = manager.add(
        content_id=content_id,
        title=details.title,
        cover_image=details.cover_image,
        content_type="series" if details.episodes and len(details.episodes) > 1 else "movie",
        provider=provider_name
    )
    
    console.print(f"[green]✓ Added to favorites: {fav.title}[/]")


@favorites.command("remove")
@click.argument("content_id")
@click.option("--provider", "-p", default=None, help="Provider name")
def favorites_remove(content_id: str, provider: Optional[str]):
    """Remove content from favorites."""
    config = get_config()
    provider_name = provider or config.default_provider
    
    manager = get_favorites_manager()
    
    if manager.remove(provider_name, content_id):
        console.print("[green]✓ Removed from favorites[/]")
    else:
        console.print("[yellow]Not found in favorites[/]")


@main.command()
@click.option("--show", is_flag=True, help="Show current configuration")
@click.option("--player", type=click.Choice(["mpv", "vlc"]), help="Set default player")
@click.option("--provider", type=click.Choice(get_all_provider_names()), help="Set default provider")
@click.option("--download-dir", type=click.Path(), help="Set download directory")
@click.option("--proxy", help="Set Cloudflare Worker Proxy URL")
def config(show: bool, player: Optional[str], provider: Optional[str], download_dir: Optional[str], proxy: Optional[str]):
    """View or edit configuration."""
    config = get_config()
    
    if show or not (player or provider or download_dir or proxy):
        table = Table(title="Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Default Player", config.default_player)
        table.add_row("Default Provider", config.default_provider)
        table.add_row("Download Directory", config.download_dir)
        table.add_row("Preferred Quality", config.preferred_quality)
        table.add_row("Proxy URL", config.proxy_url or "(none)")
        
        console.print(table)
        return
    
    if player:
        config.default_player = player
    if provider:
        config.default_provider = provider
    if download_dir:
        config.download_dir = download_dir
    if proxy:
        config.proxy_url = proxy
        # Update current session too
        set_proxy_url(proxy)
    
    save_config(config)
    console.print("[green]✓ Configuration saved[/]")


@main.command("home")
@click.option("--provider", "-p", default=None, help="Provider name")
def home_cmd(provider: Optional[str]):
    """Show home page content."""
    config = get_config()
    provider_name = provider or config.default_provider
    
    prov = get_provider_instance(provider_name)
    if not prov:
        console.print(f"[red]Provider '{provider_name}' not found[/]")
        return
    
    console.print(f"[dim]Loading home from {prov.name}...[/]")
    
    async def do_fetch():
        return await prov.fetch_home(1)
    
    rows = run_async(do_fetch())
    
    if not rows:
        console.print("[yellow]No content found[/]")
        return
    
    for row in rows[:5]:  # Limit to 5 rows
        console.print(f"\n[bold magenta]{row.name}[/]")
        for item in row.contents[:10]:  # Limit to 10 items per row
            console.print(f"  [cyan]•[/] {item.title or item.id} [dim]({item.id})[/]")


# ===== INTERACTIVE MODE =====

def interactive_mode():
    """Run interactive TUI mode."""
    display_banner()
    config = get_config()
    current_provider = config.default_provider
    
    console.print("[dim]Type 'help' for commands, 'quit' to exit[/]\n")
    
    while True:
        try:
            cmd = Prompt.ask(f"[bold cyan]meowtv[/] [dim]({current_provider})[/]").strip()
            
            if not cmd:
                continue
            
            parts = cmd.split(maxsplit=1)
            action = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            if action in ("quit", "exit", "q"):
                console.print("[dim]Goodbye! 🐱[/]")
                break
            
            elif action == "help":
                console.print("""
[bold]Commands:[/]
  [cyan]search <query>[/]    - Search for content
  [cyan]home[/]              - Show home page
  [cyan]details <id>[/]      - Show content details  
  [cyan]play <id>[/]         - Play content
  [cyan]download <id>[/]     - Download content
  [cyan]favorites[/]         - List favorites
  [cyan]provider <name>[/]   - Switch provider
  [cyan]config[/]            - Show configuration
  [cyan]quit[/]              - Exit
                """)
            
            elif action == "search" and args:
                prov = get_provider_instance(current_provider)
                if prov:
                    results = run_async(prov.search(args))
                    if results:
                        display_content_table(results)
                    else:
                        console.print("[yellow]No results[/]")
            
            elif action == "home":
                prov = get_provider_instance(current_provider)
                if prov:
                    rows = run_async(prov.fetch_home(1))
                    for row in rows[:5]:
                        console.print(f"\n[bold magenta]{row.name}[/]")
                        for item in row.contents[:8]:
                            console.print(f"  • {item.title or item.id}")
            
            elif action == "details" and args:
                prov = get_provider_instance(current_provider)
                if prov:
                    details = run_async(prov.fetch_details(args))
                    if details:
                        display_details(details)
                    else:
                        console.print("[red]Not found[/]")
            
            elif action == "play" and args:
                prov = get_provider_instance(current_provider)
                if prov:
                    details = run_async(prov.fetch_details(args))
                    if details and details.episodes:
                        ep_id = details.episodes[0].id
                        stream = run_async(prov.fetch_stream(args, ep_id))
                        if stream:
                            console.print(f"[green]▶ Playing: {details.title}[/]")
                            run_async(play(stream, title=details.title, suppress_output=("meowverse" not in prov.name.lower())))
                        else:
                            console.print("[red]Failed to load stream[/]")
                    else:
                        console.print("[red]Content not found[/]")
            
            elif action == "download" and args:
                prov = get_provider_instance(current_provider)
                if prov:
                    details = run_async(prov.fetch_details(args))
                    if details and details.episodes:
                        ep_id = details.episodes[0].id
                        stream = run_async(prov.fetch_stream(args, ep_id))
                        if stream:
                            result = download(stream, details.title)
                            if result:
                                console.print(f"[green]✓ Downloaded: {result}[/]")
                            else:
                                console.print("[red]Download failed[/]")
                        else:
                            console.print("[red]Failed to load stream[/]")
                    else:
                        console.print("[red]Content not found[/]")
            
            elif action == "favorites":
                display_favorites()
            
            elif action == "provider":
                if args and args.lower() in get_all_provider_names():
                    current_provider = args.lower()
                    console.print(f"[green]Switched to {current_provider}[/]")
                else:
                    console.print(f"[yellow]Available: {', '.join(get_all_provider_names())}[/]")
            
            elif action == "config":
                config = get_config()
                console.print(f"Player: {config.default_player}")
                console.print(f"Provider: {config.default_provider}")
                console.print(f"Download dir: {config.download_dir}")
            
            else:
                console.print(f"[red]Unknown command. Type 'help' for options.[/]")
        
        except KeyboardInterrupt:
            console.print("\n[dim]Use 'quit' to exit[/]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")


if __name__ == "__main__":
    main()
