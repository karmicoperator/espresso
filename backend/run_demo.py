#!/usr/bin/env python3
"""
Demo script to run the pipeline and save/render the generated Manim code.

This script:
1. Runs the full pipeline on a test paper (Attention Is All You Need)
2. Saves the generated Manim code to files in generated_output/
3. Optionally renders the videos using Manim

Usage (from the backend/ directory):
    uv run python run_demo.py                         # Generate and save code
    uv run python run_demo.py --render                # Also render videos
    uv run python run_demo.py --render --quality low  # Faster render for testing
    uv run python run_demo.py --verbose               # Show detailed agent logs
    uv run python run_demo.py --max 3                 # Generate up to 3 visualizations
"""

import asyncio
import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from models.paper import ArxivPaperMeta, Equation, Section, StructuredPaper
from agents.pipeline import generate_visualizations


# ============================================================
# LOGGING CONFIGURATION
# ============================================================

class ColorFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    def format(self, record):
        # Add color to level name
        color = self.COLORS.get(record.levelname, '')
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # Format the message with colors
        if record.levelname == 'INFO':
            formatted = f"{self.BOLD}{color}[{timestamp}] {record.getMessage()}{self.RESET}"
        else:
            formatted = f"{color}[{timestamp}] [{record.levelname}] {record.getMessage()}{self.RESET}"
        
        return formatted


def setup_logging(verbose: bool = False):
    """Configure logging for the demo."""
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Add console handler with color formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(ColorFormatter())
    root_logger.addHandler(console_handler)
    
    # Set levels for specific loggers
    logging.getLogger('agents.pipeline').setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('agents.section_analyzer').setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('agents.visualization_planner').setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('agents.manim_generator').setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('agents.code_validator').setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('agents.spatial_validator').setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('agents.render_tester').setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Suppress noisy third-party loggers
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('anthropic').setLevel(logging.WARNING)


def print_header(text: str):
    """Print a styled header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_step(step: int, text: str):
    """Print a pipeline step."""
    print(f"\n\033[1m\033[34m[Step {step}]\033[0m {text}")


def print_agent(agent_name: str, action: str):
    """Print an agent action."""
    print(f"  \033[36m{agent_name}\033[0m: {action}")


def print_success(text: str):
    """Print success message."""
    print(f"\033[32m✓ {text}\033[0m")


def print_warning(text: str):
    """Print warning message."""
    print(f"\033[33m⚠ {text}\033[0m")


def print_error(text: str):
    """Print error message."""
    print(f"\033[31m✗ {text}\033[0m")


# Output directory for generated code
OUTPUT_DIR = Path(__file__).parent / "generated_output"


def create_attention_paper() -> StructuredPaper:
    """Create a test paper based on 'Attention Is All You Need'."""
    meta = ArxivPaperMeta(
        arxiv_id="1706.03762",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        abstract="""The dominant sequence transduction models are based on complex 
        recurrent or convolutional neural networks. We propose a new simple network 
        architecture, the Transformer, based solely on attention mechanisms.""",
        published=datetime(2017, 6, 12),
        updated=datetime(2017, 12, 6),
        categories=["cs.CL", "cs.LG"],
        pdf_url="https://arxiv.org/pdf/1706.03762",
        html_url="https://ar5iv.org/abs/1706.03762",
    )
    
    sections = [
        Section(
            id="abstract",
            title="Abstract",
            level=1,
            content=meta.abstract,
            equations=[],
            figures=[],
            parent_id=None,
        ),
        Section(
            id="section-3-2",
            title="Scaled Dot-Product Attention",
            level=2,
            content="""An attention function can be described as mapping a query and 
            a set of key-value pairs to an output. The output is computed as a weighted 
            sum of the values, where the weight assigned to each value is computed by a 
            compatibility function of the query with the corresponding key.
            
            We compute the dot products of the query with all keys, divide each by 
            sqrt(d_k), and apply a softmax function to obtain the weights on the values.""",
            equations=[
                Equation(
                    latex=r"\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V",
                    context="The attention formula computes weighted values based on query-key similarity",
                    is_inline=False,
                ),
            ],
            figures=[],
            parent_id=None,
        ),
        Section(
            id="section-3-3",
            title="Multi-Head Attention",
            level=2,
            content="""Instead of performing a single attention function, we linearly 
            project the queries, keys and values h times. On each of these projected 
            versions we perform the attention function in parallel, yielding outputs 
            that are concatenated and projected.""",
            equations=[
                Equation(
                    latex=r"\text{MultiHead}(Q, K, V) = \text{Concat}(\text{head}_1, ..., \text{head}_h)W^O",
                    context="Multi-head attention concatenates multiple attention outputs",
                    is_inline=False,
                ),
            ],
            figures=[],
            parent_id=None,
        ),
    ]
    
    return StructuredPaper(meta=meta, sections=sections)


async def run_demo(max_visualizations: int = 2, verbose: bool = False) -> list[Path]:
    """
    Run the pipeline and save generated code to files.
    
    Returns:
        List of paths to generated .py files
    """
    start_time = time.time()
    
    print_header("ArXiviz Demo - Generating Manim Visualizations")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Create test paper
    paper = create_attention_paper()
    print(f"\nPaper: \033[1m{paper.meta.title}\033[0m")
    print(f"Sections to analyze: {len(paper.sections)}")
    print(f"Max visualizations: {max_visualizations}")
    
    print_step(1, "Analyzing sections for visualization candidates")
    print_agent("SectionAnalyzer", "Identifying which concepts need visualization...")
    
    # Run the pipeline with timing
    pipeline_start = time.time()
    
    try:
        visualizations = await generate_visualizations(paper, max_visualizations=max_visualizations)
    except Exception as e:
        print_error(f"Pipeline failed with error: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    pipeline_time = time.time() - pipeline_start
    
    if not visualizations:
        print_warning("No visualizations generated!")
        print("\nPossible reasons:")
        print("  - API key not set (check .env file)")
        print("  - No visualization candidates found in sections")
        print("  - All generations failed validation")
        return []
    
    print_success(f"Generated {len(visualizations)} visualization(s) in {pipeline_time:.1f}s")
    
    # Save each visualization to a file
    print_step(5, "Saving generated Manim code")
    saved_files = []
    
    for i, viz in enumerate(visualizations, 1):
        # Create filename from concept
        filename = viz.concept.lower().replace(" ", "_").replace("-", "_")
        filename = "".join(c for c in filename if c.isalnum() or c == "_")
        filepath = OUTPUT_DIR / f"{filename}.py"
        
        # Save the code
        filepath.write_text(viz.manim_code)
        saved_files.append(filepath)
        
        print(f"\n  \033[1m[{i}/{len(visualizations)}] {viz.concept}\033[0m")
        print(f"      File: {filepath.name}")
        print(f"      Code: {len(viz.manim_code)} chars, ~{len(viz.manim_code.splitlines())} lines")
        print(f"      Status: {viz.status}")
    
    # Print summary
    total_time = time.time() - start_time
    print_header("Summary")
    print(f"  Total time: {total_time:.1f}s")
    print(f"  Visualizations: {len(visualizations)}")
    print(f"  Output directory: {OUTPUT_DIR}")
    
    # Show first 20 lines of first visualization as preview
    if saved_files and verbose:
        print("\n\033[1mPreview of first visualization:\033[0m")
        first_code = saved_files[0].read_text()
        preview_lines = first_code.split('\n')[:25]
        for i, line in enumerate(preview_lines, 1):
            print(f"  \033[90m{i:3d}|\033[0m {line}")
        if len(first_code.split('\n')) > 25:
            print(f"  \033[90m... and {len(first_code.split(chr(10))) - 25} more lines\033[0m")
    
    return saved_files


def render_video(filepath: Path, quality: str = "medium", has_voiceover: bool = True) -> bool:
    """
    Render a Manim video from a Python file.
    
    Args:
        filepath: Path to the .py file
        quality: 'low' (480p), 'medium' (720p), 'high' (1080p)
        has_voiceover: If True, adds --disable_caching flag required for voiceover sync
    
    Returns:
        True if rendering succeeded
    """
    quality_flags = {
        "low": "-ql",      # 480p, faster
        "medium": "-qm",   # 720p
        "high": "-qh",     # 1080p
    }
    
    flag = quality_flags.get(quality, "-qm")
    
    print(f"\n🎬 Rendering: {filepath.name}")
    print(f"   Quality: {quality}")
    print(f"   Voiceover: {'Yes (--disable_caching)' if has_voiceover else 'No'}")
    
    # Build command - add --disable_caching for voiceover sync to work
    # Use system Python's manim since uv env may not have manim-voiceover installed
    # due to dependency conflicts with python-dotenv
    SYSTEM_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
    
    # Try system Python first (has manim-voiceover), fall back to uv run manim
    if Path(SYSTEM_PYTHON).exists():
        cmd = [SYSTEM_PYTHON, "-m", "manim", flag, str(filepath)]
    else:
        cmd = ["uv", "run", "manim", flag, str(filepath)]
    
    if has_voiceover:
        cmd.append("--disable_caching")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(filepath.parent),
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            print(f"   ✅ Render complete!")
            # Find the output video
            media_dir = filepath.parent / "media" / "videos"
            if media_dir.exists():
                print(f"   📹 Videos saved to: {media_dir}")
            return True
        else:
            print(f"   ❌ Render failed:")
            print(result.stderr[:500] if result.stderr else "Unknown error")
            return False
            
    except FileNotFoundError:
        print("   ❌ Manim not installed! Install with: pip install manim")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run ArXiviz demo - Generate Manim visualizations from papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python run_demo.py                    # Generate visualizations
  uv run python run_demo.py --verbose          # Show detailed agent logs
  uv run python run_demo.py --render           # Generate and render videos
  uv run python run_demo.py --max 3            # Generate up to 3 visualizations
        """
    )
    parser.add_argument("--render", action="store_true", help="Render videos after generation")
    parser.add_argument("--quality", choices=["low", "medium", "high"], default="medium",
                        help="Render quality (default: medium)")
    parser.add_argument("--max", type=int, default=2, help="Max visualizations to generate")
    parser.add_argument("--verbose", "-v", action="store_true", 
                        help="Show detailed agent logs (DEBUG level)")
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(verbose=args.verbose)
    
    # Show configuration
    print("\n\033[1mConfiguration:\033[0m")
    print(f"  Verbose logging: {'Yes' if args.verbose else 'No'}")
    print(f"  Max visualizations: {args.max}")
    print(f"  Render videos: {'Yes' if args.render else 'No'}")
    
    # Check for API key
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("MARTIAN_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print_error("No API key found!")
        print("  Set ANTHROPIC_API_KEY or MARTIAN_API_KEY in .env file")
        print("  Copy .env.example to .env and add your key")
        sys.exit(1)
    
    api_provider = "Martian" if os.getenv("MARTIAN_API_KEY") else "Anthropic"
    print(f"  API Provider: {api_provider}")
    print(f"  API Key: {api_key[:8]}...{api_key[-4:]}")
    
    # Run the pipeline
    try:
        saved_files = asyncio.run(run_demo(max_visualizations=args.max, verbose=args.verbose))
    except KeyboardInterrupt:
        print_warning("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    if not saved_files:
        sys.exit(1)
    
    # Render if requested
    if args.render:
        print_header("Rendering Videos")
        
        success_count = 0
        for filepath in saved_files:
            if render_video(filepath, args.quality):
                success_count += 1
        
        print(f"\nRendered {success_count}/{len(saved_files)} videos successfully")
    else:
        print_header("Next Steps")
        print("\nTo render the generated Manim code:")
        print(f"  1. cd {OUTPUT_DIR}")
        print("  2. uv run manim -qm <filename>.py")
        print("\nOr run this script with --render:")
        print("  uv run python run_demo.py --render")
        print("  uv run python run_demo.py --render --quality low   # Faster (480p)")
        print("\nOutput videos will be in:")
        print(f"  {OUTPUT_DIR}/media/videos/")


if __name__ == "__main__":
    main()
