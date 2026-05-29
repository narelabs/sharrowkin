"""Learning and adaptation subsystem for Sharrowkin agent.

Provides continuous improvement through:
- Failure analysis
- Strategy optimization
- Code style learning
- Meta-learning
"""

from .failure_analyzer import FailureAnalyzer, FailureContext
from .strategy_optimizer import StrategyOptimizer, Strategy
from .style_learner import StyleLearner, CodeStyle
from .meta_learner import MetaLearner, LearningMetrics

__all__ = [
    "FailureAnalyzer",
    "FailureContext",
    "StrategyOptimizer",
    "Strategy",
    "StyleLearner",
    "CodeStyle",
    "MetaLearner",
    "LearningMetrics",
]
