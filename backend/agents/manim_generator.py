"""Manim Generator Agent - Generates Manim Python code from visualization plans."""

import re
import sys
from pathlib import Path

# Handle both package and direct imports
try:
    from .base import BaseAgent
    from ..models.generation import (
        VisualizationPlan,
        GeneratedCode,
        VisualizationType,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agents.base import BaseAgent
    from models.generation import (
        VisualizationPlan,
        GeneratedCode,
        VisualizationType,
    )


class ManimGenerator(BaseAgent):
    """
    Generates working Manim Python code from visualization plans.

    Supports two generation modes:
    - Standard mode: regular Scene/ThreeDScene output
    - Voiceover mode: VoiceoverScene with narration blocks and tracker-timed play calls
    """

    EXAMPLE_FILES = {
        VisualizationType.EQUATION: "equation_walkthrough.py",
        VisualizationType.ARCHITECTURE: "architecture_diagram.py",
        VisualizationType.DATA_FLOW: "data_flow.py",
        VisualizationType.ALGORITHM: "algorithm_steps.py",
        VisualizationType.MATRIX: "matrix_operations.py",
        VisualizationType.THREE_D: "three_d_network.py",
    }

    # Voiceover few-shot examples by visualization family
    VOICEOVER_EXAMPLE_FILES = {
        VisualizationType.EQUATION: "voiceover_equation.py",
        VisualizationType.ARCHITECTURE: "voiceover_architecture.py",
        VisualizationType.DATA_FLOW: "voiceover_data_flow.py",
        VisualizationType.ALGORITHM: "voiceover_data_flow.py",
        VisualizationType.MATRIX: "voiceover_equation.py",
        VisualizationType.THREE_D: "voiceover_architecture.py",
    }

    DEFAULT_EXAMPLE = "equation_walkthrough.py"
    DEFAULT_VOICEOVER_EXAMPLE = "voiceover_equation.py"

    TTS_SETUP = {
        "gtts": "self.set_speech_service(GTTSService())",
        "azure": 'self.set_speech_service(AzureService(voice="en-US-AriaNeural"))',
        "elevenlabs": 'self.set_speech_service(ElevenLabsService(voice_id="pNInz6obpgDQGcFmaJgB", model="eleven_flash_v2_5", transcription_model=None))',
        "recorder": "self.set_speech_service(RecorderService())",
    }

    ELEVENLABS_VOICES = {
        "Adam": "pNInz6obpgDQGcFmaJgB",
        "Antoni": "ErXwobaYiN019PkySvjV",
        "Arnold": "VR6AewLTigWG4xSOukaG",
        "Bella": "EXAVITQu4vr4xnSDxMaL",
        "Domi": "AZnzlk1XvdvUeBnXmlld",
        "Elli": "MF3mGyEYCl7XYWbV9V6O",
        "Josh": "TxGEqnHWrfWFTfGW9XjX",
        "Rachel": "21m00Tcm4TlvDq8ikWAM",
        "Sam": "yoZ06aMxZJJ28mfd3POQ",
    }

    def __init__(self, model: str | None = None):
        super().__init__("manim_generator.md", model=model, max_tokens=8192)
        self.examples = self._load_examples(self.EXAMPLE_FILES, self.DEFAULT_EXAMPLE)
        self.voiceover_examples = self._load_examples(
            self.VOICEOVER_EXAMPLE_FILES,
            self.DEFAULT_VOICEOVER_EXAMPLE,
        )

    def _get_examples_dir(self) -> Path:
        """Get the examples directory path."""
        return Path(__file__).parent.parent / "examples"

    def _load_examples(
        self,
        mapping: dict[VisualizationType, str],
        default_filename: str,
    ) -> dict[VisualizationType, str]:
        """Load few-shot examples by visualization type."""
        examples: dict[VisualizationType, str] = {}
        examples_dir = self._get_examples_dir()

        for viz_type, filename in mapping.items():
            filepath = examples_dir / filename
            if filepath.exists():
                examples[viz_type] = filepath.read_text()
            else:
                default_path = examples_dir / default_filename
                examples[viz_type] = default_path.read_text() if default_path.exists() else ""

        return examples

    def _get_example_for_type(self, viz_type: VisualizationType, voiceover_enabled: bool) -> str:
        """Get the appropriate few-shot example for a visualization type."""
        example_bank = self.voiceover_examples if voiceover_enabled else self.examples
        default_type = VisualizationType.EQUATION
        return example_bank.get(viz_type, example_bank.get(default_type, ""))

    def _get_tts_setup_snippet(self, tts_service: str, voice_name: str) -> str:
        """Return concrete set_speech_service(...) snippet for prompt grounding."""
        if tts_service == "elevenlabs":
            voice_id = self.ELEVENLABS_VOICES.get(voice_name, self.ELEVENLABS_VOICES["Adam"])
            return (
                "self.set_speech_service("
                f'ElevenLabsService(voice_id="{voice_id}", '
                'model="eleven_flash_v2_5", transcription_model=None)'
                ")"
            )

        return self.TTS_SETUP.get(tts_service, self.TTS_SETUP["gtts"])

    def _generate_scene_class_name(self, concept_name: str) -> str:
        """Generate a valid Python class name from concept name."""
        words = re.sub(r"[^a-zA-Z0-9\s]", "", concept_name).split()
        class_name = "".join(word.capitalize() for word in words)

        if class_name and not class_name[0].isalpha():
            class_name = "Viz" + class_name

        if not class_name:
            class_name = "Visualization"

        return class_name

    def _extract_scene_class_name(self, code: str) -> str:
        """Extract the scene class name from generated code."""
        match = re.search(r"class\s+(\w+)\s*\(\s*(Scene|ThreeDScene|VoiceoverScene)\s*\)", code)
        if match:
            return match.group(1)
        return "GeneratedScene"

    def _clean_code(self, code: str) -> str:
        """Clean up generated code and normalize formatting wrappers."""
        code = self._extract_code_block(code, "python")

        if "from manim import" not in code:
            code = "from manim import *\n\n" + code

        return code.strip()

    def _extract_narration_lines(self, code: str) -> list[str]:
        """Extract narration lines from `with self.voiceover(text="...")` blocks."""
        matches = re.findall(
            r'with\s+self\.voiceover\s*\(\s*text\s*=\s*"([^"]+)"\s*\)\s+as\s+tracker\s*:',
            code,
        )
        if matches:
            return [m.strip() for m in matches if m.strip()]

        # Legacy positional style fallback if model returned it.
        positional = re.findall(
            r'with\s+self\.voiceover\s*\(\s*"([^"]+)"\s*\)\s+as\s+tracker\s*:',
            code,
        )
        return [m.strip() for m in positional if m.strip()]

    def _extract_beat_labels(self, code: str) -> list[str]:
        """Extract beat labels in order, e.g. `# Beat 2:`."""
        labels = []
        for line in code.splitlines():
            stripped = line.strip()
            if re.match(r"#\s*Beat\s*\d+", stripped, re.IGNORECASE):
                labels.append(stripped)
        return labels

    def _build_prompt(
        self,
        plan: VisualizationPlan,
        voiceover_enabled: bool,
        tts_service: str,
        voice_name: str,
        narration_style: str,
        target_duration_seconds: tuple[int, int],
    ) -> str:
        """Build generation prompt with mode-specific requirements."""
        example_code = self._get_example_for_type(plan.visualization_type, voiceover_enabled)
        scene_class_name = self._generate_scene_class_name(plan.concept_name)
        tts_setup_snippet = self._get_tts_setup_snippet(tts_service, voice_name)

        return self._format_prompt(
            plan_json=plan.model_dump_json(indent=2),
            example_code=example_code,
            duration_seconds=plan.duration_seconds,
            target_min_duration=target_duration_seconds[0],
            target_max_duration=target_duration_seconds[1],
            scene_class_name=scene_class_name,
            voiceover_enabled=str(voiceover_enabled).lower(),
            tts_service=tts_service,
            voice_name=voice_name,
            narration_style=narration_style,
            tts_setup_snippet=tts_setup_snippet,
        )

    async def run(
        self,
        plan: VisualizationPlan,
        voiceover_enabled: bool = True,
        tts_service: str = "elevenlabs",
        voice_name: str = "Adam",
        narration_style: str = "concept_teacher",
        target_duration_seconds: tuple[int, int] = (30, 45),
    ) -> GeneratedCode:
        """Generate Manim code from a plan, optionally with built-in voiceovers."""
        prompt = self._build_prompt(
            plan=plan,
            voiceover_enabled=voiceover_enabled,
            tts_service=tts_service,
            voice_name=voice_name,
            narration_style=narration_style,
            target_duration_seconds=target_duration_seconds,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        code = self._clean_code(response.content[0].text)
        actual_class_name = self._extract_scene_class_name(code)
        dependencies = ["manim"]
        if voiceover_enabled:
            dependencies.append("manim_voiceover")

        return GeneratedCode(
            code=code,
            scene_class_name=actual_class_name,
            dependencies=dependencies,
            voiceover_enabled=voiceover_enabled,
            narration_lines=self._extract_narration_lines(code) if voiceover_enabled else [],
            narration_beats=self._extract_beat_labels(code) if voiceover_enabled else [],
        )

    async def run_with_feedback(
        self,
        plan: VisualizationPlan,
        previous_code: str,
        error_message: str,
        voiceover_enabled: bool = True,
        tts_service: str = "elevenlabs",
        voice_name: str = "Adam",
        narration_style: str = "concept_teacher",
        target_duration_seconds: tuple[int, int] = (30, 45),
    ) -> GeneratedCode:
        """Regenerate code with feedback from previous failures."""
        base_prompt = self._build_prompt(
            plan=plan,
            voiceover_enabled=voiceover_enabled,
            tts_service=tts_service,
            voice_name=voice_name,
            narration_style=narration_style,
            target_duration_seconds=target_duration_seconds,
        )

        error_feedback = f"""
## Previous Attempt Failed!
The previous code had issues. Fix them and regenerate complete code.

### Previous Code:
```python
{previous_code}
```

### Feedback:
{error_message}

### Mandatory Fix Expectations:
- Preserve concept accuracy and scene progression from the plan
- Keep strict narration quality (educational, concept-focused)
- If voiceover is enabled, keep tracker-timed play calls with run_time=tracker.duration
"""

        prompt = base_prompt + "\n\n" + error_feedback

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        code = self._clean_code(response.content[0].text)
        actual_class_name = self._extract_scene_class_name(code)
        dependencies = ["manim"]
        if voiceover_enabled:
            dependencies.append("manim_voiceover")

        return GeneratedCode(
            code=code,
            scene_class_name=actual_class_name,
            dependencies=dependencies,
            voiceover_enabled=voiceover_enabled,
            narration_lines=self._extract_narration_lines(code) if voiceover_enabled else [],
            narration_beats=self._extract_beat_labels(code) if voiceover_enabled else [],
        )

    def run_sync(
        self,
        plan: VisualizationPlan,
        voiceover_enabled: bool = True,
        tts_service: str = "elevenlabs",
        voice_name: str = "Adam",
        narration_style: str = "concept_teacher",
        target_duration_seconds: tuple[int, int] = (30, 45),
    ) -> GeneratedCode:
        """Synchronous version for testing."""
        prompt = self._build_prompt(
            plan=plan,
            voiceover_enabled=voiceover_enabled,
            tts_service=tts_service,
            voice_name=voice_name,
            narration_style=narration_style,
            target_duration_seconds=target_duration_seconds,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        code = self._clean_code(response.content[0].text)
        actual_class_name = self._extract_scene_class_name(code)
        dependencies = ["manim"]
        if voiceover_enabled:
            dependencies.append("manim_voiceover")

        return GeneratedCode(
            code=code,
            scene_class_name=actual_class_name,
            dependencies=dependencies,
            voiceover_enabled=voiceover_enabled,
            narration_lines=self._extract_narration_lines(code) if voiceover_enabled else [],
            narration_beats=self._extract_beat_labels(code) if voiceover_enabled else [],
        )
