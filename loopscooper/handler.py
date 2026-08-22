import logging
import os
import sys
from typing import List, Optional, Tuple

from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.table import Table

from loopscooper.analysis import LoopPair
from loopscooper.bpm import detect_bpm, get_suggested_loop_durations
from loopscooper.console import rich_console
from loopscooper.core import MusicLooper


class LoopHandler:
    def __init__(self, *, filepath: str):
        self.filepath = filepath
        self._musiclooper = MusicLooper(filepath=filepath)

        logging.info(f"Loaded \"{filepath}\". Detecting BPM...")

        self.bpm, _ = detect_bpm(filepath)
        self.suggestions = get_suggested_loop_durations(self.bpm)

        logging.info(f"BPM detected: {self.bpm:.2f}")

        self.loop_pair_list: List[LoopPair] = []
        self.current_min_duration: float = self.suggestions["one_bar"]
        self.current_max_duration: float = self.suggestions["two_bars"]

    @property
    def musiclooper(self) -> MusicLooper:
        """Returns the handler's `MusicLooper` instance."""
        return self._musiclooper

    def play_looping(self, loop_start: int, loop_end: int):
        self.musiclooper.play_looping(loop_start, loop_end)

    def display_loops(self, show_top: int = 25):
        """Display the discovered loop points in a table."""
        total_candidates = len(self.loop_pair_list)
        _display_more_hint_msg = "\nEnter 'more' to display additional loop points, 'all' to display all of them, or 'reset' to display the default amount." if show_top < total_candidates else ""
        _discovered_points_msg = f"Discovered loop points\n({min(show_top, total_candidates)}/{total_candidates} displayed)"
        table = Table(title=_discovered_points_msg, caption=_display_more_hint_msg)
        table.add_column("Index", justify="right", style="cyan", no_wrap=True)
        table.add_column("Loop Start", style="magenta")
        table.add_column("Loop End", style="green")
        table.add_column("Length", style="white")

        for idx, pair in enumerate(self.loop_pair_list[:show_top]):
            start_time = self.musiclooper.samples_to_ftime(pair.loop_start)
            end_time = self.musiclooper.samples_to_ftime(pair.loop_end)
            length = self.musiclooper.samples_to_ftime(pair.loop_end - pair.loop_start)
            table.add_row(str(idx), str(start_time), str(end_time), str(length))

        rich_console.print(table)
        rich_console.print()

        return show_top, total_candidates

    def detect_loops(self, min_duration: float, max_duration: float, approx_start: Optional[float] = None, approx_end: Optional[float] = None):
        """Run loop detection with the given duration constraints."""
        logging.info(f"Analyzing audio for loops ({min_duration:.1f}-{max_duration:.1f}s)...")

        self.loop_pair_list = self.musiclooper.find_loop_pairs(
            min_duration_multiplier=0.35,
            min_loop_duration=min_duration,
            max_loop_duration=max_duration,
            approx_loop_start=approx_start,
            approx_loop_end=approx_end,
            brute_force=False,
            disable_pruning=False,
        )

    def prompt_duration_window(self, default_min: float, default_max: float) -> Tuple[float, float]:
        """Prompt user for loop duration window (min,max in seconds)."""
        default_str = f"{default_min:.1f},{default_max:.1f}"
        while True:
            user_input = rich_console.input(f"Enter loop duration window (min,max in seconds) [{default_str}]:").strip()

            if not user_input:
                return default_min, default_max

            try:
                parts = user_input.split(",")
                if len(parts) != 2:
                    rich_console.print("[red]Please enter two values separated by a comma (e.g., 2,8)[/]")
                    continue

                min_dur = float(parts[0].strip())
                max_dur = float(parts[1].strip())

                if min_dur <= 0 or max_dur <= 0:
                    rich_console.print("[red]Duration values must be positive numbers.[/]")
                    continue

                if min_dur >= max_dur:
                    rich_console.print("[red]Minimum duration must be less than maximum duration.[/]")
                    continue

                return min_dur, max_dur

            except ValueError:
                rich_console.print("[red]Please enter valid numbers (e.g., 2,8)[/]")

    def prompt_redetect(self, current_min: float, current_max: float) -> Tuple[str, Optional[float], Optional[float]]:
        """Prompt user to re-detect loops with new duration constraints.
        
        Returns:
            Tuple of (action, min_duration, max_duration)
            action is "n" to skip, "redetect" to re-detect with new constraints
        """
        default_str = "n"
        while True:
            user_input = rich_console.input(f"Re-detect loops? (enter min,max duration or n) [{default_str}]:").strip()

            if not user_input:
                return "n", None, None

            if user_input.lower() == "n":
                return "n", None, None

            try:
                parts = user_input.split(",")
                if len(parts) != 2:
                    rich_console.print("[red]Please enter two values separated by a comma (e.g., 2,6)[/]")
                    continue

                min_dur = float(parts[0].strip())
                max_dur = float(parts[1].strip())

                if min_dur <= 0 or max_dur <= 0:
                    rich_console.print("[red]Duration values must be positive numbers.[/]")
                    continue

                if min_dur >= max_dur:
                    rich_console.print("[red]Minimum duration must be less than maximum duration.[/]")
                    continue

                return "redetect", min_dur, max_dur

            except ValueError:
                rich_console.print("[red]Please enter valid numbers (e.g., 2,6)[/]")

    def interactive_preview(self, show_top: int = 25):
        """Interactive loop preview with pagination."""
        total_candidates = len(self.loop_pair_list)

        while True:
            show_top, _ = self.display_loops(show_top)

            user_input = rich_console.input("Preview loop index (e.g., 0p, or \"done\" to skip):").strip()

            if not user_input:
                continue

            if user_input.lower() == "done":
                return

            if user_input.lower() == "more":
                show_top = min(show_top * 2, total_candidates)
                continue

            if user_input.lower() == "all":
                show_top = total_candidates
                continue

            if user_input.lower() == "reset":
                show_top = 25
                continue

            # Check if input is a preview request
            if user_input.endswith("p"):
                try:
                    idx = int(user_input[:-1])
                except ValueError:
                    rich_console.print(f"[red]Please enter a valid index number.[/]")
                    continue

                if not 0 <= idx < len(self.loop_pair_list):
                    rich_console.print(f"[red]Invalid index: {idx}. Range is [0,{len(self.loop_pair_list)-1}].[/]")
                    continue

                pair = self.loop_pair_list[idx]
                rich_console.print(f"[bold]Previewing loop #{idx}...[/] (Ctrl+C to stop)")
                try:
                    self.play_looping(pair.loop_start, pair.loop_end)
                except KeyboardInterrupt:
                    rich_console.print()
                    continue
            else:
                try:
                    idx = int(user_input)
                    if not 0 <= idx < len(self.loop_pair_list):
                        raise IndexError
                    rich_console.print(f"[red]To preview, append 'p' to the index (e.g., {idx}p).[/]")
                except ValueError:
                    rich_console.print(f"[red]Invalid input: {user_input}.[/]")

    def parse_loop_selection(self, selection_str: str) -> List[int]:
        """Parse user loop selection string into a list of loop indices.

        Accepts comma-separated values:
        - Single numbers: "0"
        - Multiple: "0,1,3"
        - Ranges: "1-4"
        - Mixed: "0,1-3,5-8,10"

        Args:
            selection_str (str): User's selection string

        Returns:
            List[int]: List of loop indices to export
        """
        selected_indices = []
        seen = set()

        # Split by comma to handle comma-separated values
        parts = selection_str.strip().split(",")

        for part in parts:
            part = part.strip()

            # Check for range
            if "-" in part:
                try:
                    start, end = part.split("-")
                    start_idx = int(start)
                    end_idx = int(end)
                    if start_idx > end_idx:
                        raise ValueError("Start index must be less than end index")
                    for i in range(start_idx, end_idx + 1):
                        if 0 <= i < len(self.loop_pair_list) and i not in seen:
                            selected_indices.append(i)
                            seen.add(i)
                except ValueError as e:
                    if "Start index" in str(e):
                        raise
                    rich_console.print(f"[red]Invalid range format: {part}[/]")
                    raise
            else:
                try:
                    idx = int(part)
                    if 0 <= idx < len(self.loop_pair_list) and idx not in seen:
                        selected_indices.append(idx)
                        seen.add(idx)
                except ValueError:
                    rich_console.print(f"[red]Invalid input: {part}[/]")
                    raise

        if not selected_indices:
            raise ValueError("No valid loop indices selected")

        return selected_indices

    def export_selected_loops(self, selected_indices: List[int], output_dir: str, format: str = "WAV") -> List[str]:
        """Export selected loops to WAV files in the output directory.

        Files are named {basename}-{NN}.wav (e.g., song-01.wav, song-02.wav)

        Args:
            selected_indices (List[int]): List of loop indices to export
            output_dir (str): Output directory path
            format (str, optional): Audio format. Defaults to "WAV".

        Returns:
            List[str]: List of exported file paths
        """
        os.makedirs(output_dir, exist_ok=True)

        basename = os.path.splitext(os.path.basename(self.filepath))[0]
        exported_files = []

        for idx, loop_idx in enumerate(selected_indices, 1):
            pair = self.loop_pair_list[loop_idx]
            filename = f"{basename}-{idx:02d}.{format.lower()}"
            output_path = os.path.join(output_dir, filename)

            self.musiclooper.export_single_loop(
                pair.loop_start,
                pair.loop_end,
                output_path,
                format=format,
            )
            exported_files.append(output_path)

            loop_length = self.musiclooper.samples_to_ftime(pair.loop_end - pair.loop_start)
            rich_console.print(f"Exported [green]{filename}[/] ({loop_length})")

        return exported_files

    def run(self):
        """Run the complete interactive workflow."""
        # Phase 1: Display BPM detection
        rich_console.print()
        rich_console.print(f"[bold cyan]Detected BPM:[/] {self.bpm:.2f}")
        rich_console.print(f"[bold cyan]Beat Duration:[/] {self.suggestions['beat_duration']:.3f}s")
        rich_console.print()
        rich_console.print("[bold]Suggested Loop Lengths (4/4 time):[/]")
        rich_console.print(f"  [bold green]1 bar (4 beats):[/] {self.suggestions['one_bar']:.3f}s")
        rich_console.print(f"  [bold yellow]2 bars (8 beats):[/] {self.suggestions['two_bars']:.3f}s")

        # Phase 2: Duration window prompt
        min_dur, max_dur = self.prompt_duration_window(
            self.suggestions["one_bar"],
            self.suggestions["two_bars"]
        )
        self.current_min_duration = min_dur
        self.current_max_duration = max_dur

        # Phase 3: Detect loops
        self.detect_loops(min_dur, max_dur)

        if not self.loop_pair_list:
            rich_console.print("[red]No loops found with the specified duration constraints.[/]")
            return

        # Phase 4-5: Preview and re-detect loop
        while True:
            self.interactive_preview()

            action, new_min, new_max = self.prompt_redetect(
                self.current_min_duration,
                self.current_max_duration
            )

            if action == "n":
                break

            # Re-detect with new constraints
            self.current_min_duration = new_min
            self.current_max_duration = new_max
            self.detect_loops(new_min, new_max)

            if not self.loop_pair_list:
                rich_console.print("[red]No loops found with the specified duration constraints.[/]")
                return

        # Phase 6: Export
        while True:
            user_input = rich_console.input("Enter loop indices to export (e.g., 0,1-3,5-8,10):").strip()

            if not user_input:
                rich_console.print("[red]No loops selected. Exiting.[/]")
                return

            try:
                selected_indices = self.parse_loop_selection(user_input)
                break
            except (ValueError, IndexError) as e:
                rich_console.print(f"[red]Error: {e}[/]")
                continue

        # Determine output directory
        basename = os.path.splitext(os.path.basename(self.filepath))[0]
        output_dir = os.path.join(os.path.dirname(os.path.abspath(self.filepath)), f"{basename}-samples")

        rich_console.print(f"\nExporting {len(selected_indices)} loop(s) to [green]{output_dir}/[/]...")
        exported_files = self.export_selected_loops(selected_indices, output_dir)

        rich_console.print()
        rich_console.print(f"[bold green]Successfully exported {len(exported_files)} loop(s) to {output_dir}/[/]")
