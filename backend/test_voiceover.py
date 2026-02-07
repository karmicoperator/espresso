"""
Test script for voiceover integration.

This creates a simple Manim scene with AI-generated voiceover.

Usage:
    python3 test_voiceover.py           # Generate gTTS test (free, no API key needed)
    python3 test_voiceover.py --render  # Also render the scene
    python3 test_voiceover.py --elevenlabs  # Use ElevenLabs (requires voices_read permission)

Notes:
- ElevenLabs requires ELEVEN_API_KEY with "voices_read" AND "text_to_speech" permissions
- gTTS is free but requires internet connection
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check for ElevenLabs API key
use_elevenlabs = "--elevenlabs" in sys.argv
eleven_api_key = os.environ.get("ELEVEN_API_KEY")

if use_elevenlabs:
    if not eleven_api_key:
        print("ERROR: ELEVEN_API_KEY environment variable not set!")
        print("Please add it to your .env file or set it in your environment.")
        exit(1)
    print(f"ElevenLabs API key found: {eleven_api_key[:10]}...")
    print("\nNOTE: ElevenLabs requires 'voices_read' permission in your API key.")
    print("      If you get a permission error, go to your ElevenLabs dashboard")
    print("      and add 'voices_read' permission to your API key.")
    tts_service = "elevenlabs"
else:
    print("Using gTTS (free, no API key required)")
    print("Tip: Use --elevenlabs flag for higher quality ElevenLabs voices")
    tts_service = "gtts"

# Test scene code templates
ELEVENLABS_SCENE_CODE = '''"""Test scene with ElevenLabs voiceover."""
from manim import *
from manim_voiceover import VoiceoverScene
from manim_voiceover.services.elevenlabs import ElevenLabsService


class VoiceoverTestScene(VoiceoverScene):
    """Simple test scene demonstrating ElevenLabs voiceover integration."""
    
    def construct(self):
        # Initialize ElevenLabs TTS service
        # Note: Requires ELEVEN_API_KEY with 'voices_read' and 'text_to_speech' permissions
        # model="eleven_flash_v2_5" - fastest and cheapest option
        # transcription_model=None disables whisper (incompatible with Python 3.13)
        service = ElevenLabsService(
            voice_id="pNInz6obpgDQGcFmaJgB",  # Adam voice
            model="eleven_flash_v2_5",  # Fastest and cheapest
            voice_settings={"stability": 0.5, "similarity_boost": 0.5},
            transcription_model=None,  # Disable whisper transcription
        )
        self.set_speech_service(service)'''

GTTS_SCENE_CODE = '''"""Test scene with gTTS voiceover (free, no API key needed)."""
from manim import *
from manim_voiceover import VoiceoverScene
from manim_voiceover.services.gtts import GTTSService


class VoiceoverTestScene(VoiceoverScene):
    """Simple test scene demonstrating gTTS voiceover integration."""
    
    def construct(self):
        # Initialize gTTS service (free, uses Google Translate API)
        # transcription_model=None disables whisper (incompatible with Python 3.13)
        self.set_speech_service(GTTSService(transcription_model=None))'''

# Common scene body (animation code)
SCENE_BODY = '''
        
        # Introduction
        with self.voiceover("Welcome to this visualization demo. Let me show you how voiceovers sync with animations.") as tracker:
            title = Text("Voiceover Demo", font_size=48)
            self.play(Write(title), run_time=tracker.duration)
        
        self.wait(0.5)
        
        # Move title and show circle
        with self.voiceover("Watch as I create a circle on the screen.") as tracker:
            self.play(title.animate.to_edge(UP), run_time=tracker.duration * 0.3)
            circle = Circle(color=BLUE, radius=1.5)
            self.play(Create(circle), run_time=tracker.duration * 0.7)
        
        # Transform to square
        with self.voiceover("Now let's transform this circle into a square.") as tracker:
            square = Square(side_length=3, color=GREEN)
            self.play(Transform(circle, square), run_time=tracker.duration)
        
        # Conclusion
        with self.voiceover("That's the power of synchronized animations and voiceovers. Thank you for watching!") as tracker:
            self.play(FadeOut(circle), FadeOut(title), run_time=tracker.duration)
        
        self.wait(1)
'''

# Select the appropriate scene code based on TTS service
if tts_service == "elevenlabs":
    TEST_SCENE_CODE = ELEVENLABS_SCENE_CODE + SCENE_BODY
else:
    TEST_SCENE_CODE = GTTS_SCENE_CODE + SCENE_BODY

# Create the test scene file
output_dir = Path(__file__).parent / "generated_output"
output_dir.mkdir(exist_ok=True)

test_scene_file = output_dir / "voiceover_test_scene.py"
test_scene_file.write_text(TEST_SCENE_CODE)

print(f"\nGenerated test scene ({tts_service}): {test_scene_file}")
print("\nTo render the scene with voiceover, run:")
print(f"  cd {output_dir}")
print(f"  manim -pql voiceover_test_scene.py VoiceoverTestScene --disable_caching")
print("\nNote: --disable_caching is required for voiceover sync to work correctly.")

# Optionally try to render
if "--render" in sys.argv:
    import subprocess
    print("\n" + "=" * 50)
    print("Attempting to render scene...")
    print("=" * 50 + "\n")
    
    result = subprocess.run(
        ["/Library/Frameworks/Python.framework/Versions/3.13/bin/python3", "-m", "manim", 
         "-ql", "voiceover_test_scene.py", "VoiceoverTestScene", "--disable_caching"],
        cwd=output_dir,
        capture_output=False,
    )
    
    if result.returncode == 0:
        print("\nScene rendered successfully!")
        print(f"Check {output_dir}/media/videos/ for the output.")
    else:
        print(f"\nRendering failed with exit code {result.returncode}")
else:
    print("\nTip: Run with --render flag to automatically render the scene:")
    print(f"  python3 test_voiceover.py --render")
