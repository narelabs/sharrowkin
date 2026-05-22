"""Audio system for persona sound effects.

This module provides audio playback capabilities for persona themes,
including ambient sounds, action sounds, and event-triggered effects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable


class AudioPlayer:
    """Simple audio player for persona sound effects.

    Note: This is a placeholder implementation. In production, this would
    integrate with Howler.js on the frontend or use a Python audio library
    like pygame or sounddevice for backend playback.
    """

    def __init__(self, audio_base_path: Path | None = None) -> None:
        self.audio_base_path = audio_base_path or Path(__file__).parent.parent / "audio"
        self.enabled = True
        self.volume = 0.7
        self.ambient_playing = False
        self.event_callbacks: list[Callable[[str, str], None]] = []

    def play(self, audio_file: str, loop: bool = False) -> None:
        """Play an audio file.

        Args:
            audio_file: Relative path to audio file (e.g., "mechanicus/gear_click.mp3")
            loop: Whether to loop the audio
        """
        if not self.enabled:
            return

        audio_path = self.audio_base_path / audio_file

        # Placeholder: In production, this would actually play audio
        print(f"🔊 [Audio] Playing: {audio_file} (volume: {self.volume}, loop: {loop})")

        # Trigger callbacks
        for callback in self.event_callbacks:
            callback("play", audio_file)

    def play_ambient(self, audio_file: str) -> None:
        """Play ambient background audio (looped).

        Args:
            audio_file: Relative path to ambient audio file
        """
        if self.ambient_playing:
            self.stop_ambient()

        self.play(audio_file, loop=True)
        self.ambient_playing = True

    def stop_ambient(self) -> None:
        """Stop ambient background audio."""
        if not self.ambient_playing:
            return

        print("🔇 [Audio] Stopping ambient audio")
        self.ambient_playing = False

        # Trigger callbacks
        for callback in self.event_callbacks:
            callback("stop_ambient", "")

    def set_volume(self, volume: float) -> None:
        """Set audio volume (0.0 to 1.0).

        Args:
            volume: Volume level between 0.0 (mute) and 1.0 (max)
        """
        self.volume = max(0.0, min(1.0, volume))
        print(f"🔊 [Audio] Volume set to: {self.volume * 100:.0f}%")

    def enable(self) -> None:
        """Enable audio playback."""
        self.enabled = True
        print("🔊 [Audio] Enabled")

    def disable(self) -> None:
        """Disable audio playback."""
        self.enabled = False
        self.stop_ambient()
        print("🔇 [Audio] Disabled")

    def add_event_callback(self, callback: Callable[[str, str], None]) -> None:
        """Add a callback for audio events.

        Args:
            callback: Function that receives (event_type, audio_file)
        """
        self.event_callbacks.append(callback)


class PersonaAudioManager:
    """Manages audio playback for persona themes."""

    def __init__(self, audio_player: AudioPlayer | None = None) -> None:
        self.audio_player = audio_player or AudioPlayer()
        self.current_persona_id: str | None = None

    def activate_persona_audio(self, persona_id: str, audio_files: dict[str, str]) -> None:
        """Activate audio for a persona.

        Args:
            persona_id: ID of the persona
            audio_files: Dictionary mapping event types to audio file paths
        """
        self.current_persona_id = persona_id

        # Play ambient audio if available
        ambient_file = audio_files.get("ambient")
        if ambient_file:
            self.audio_player.play_ambient(ambient_file)

    def deactivate_persona_audio(self) -> None:
        """Deactivate current persona audio."""
        self.audio_player.stop_ambient()
        self.current_persona_id = None

    def play_event_sound(self, event_type: str, audio_files: dict[str, str]) -> None:
        """Play sound for a specific event.

        Args:
            event_type: Type of event (file_change, commit, success, error)
            audio_files: Dictionary mapping event types to audio file paths
        """
        audio_file = audio_files.get(event_type)
        if audio_file:
            self.audio_player.play(audio_file)

    def set_volume(self, volume: float) -> None:
        """Set audio volume."""
        self.audio_player.set_volume(volume)

    def enable(self) -> None:
        """Enable audio."""
        self.audio_player.enable()

    def disable(self) -> None:
        """Disable audio."""
        self.audio_player.disable()


# Global audio manager instance
_audio_manager: PersonaAudioManager | None = None


def get_audio_manager() -> PersonaAudioManager:
    """Get the global audio manager instance."""
    global _audio_manager
    if _audio_manager is None:
        _audio_manager = PersonaAudioManager()
    return _audio_manager


def play_persona_event(event_type: str, audio_files: dict[str, str]) -> None:
    """Play audio for a persona event.

    Args:
        event_type: Type of event (file_change, commit, success, error)
        audio_files: Dictionary mapping event types to audio file paths
    """
    get_audio_manager().play_event_sound(event_type, audio_files)
