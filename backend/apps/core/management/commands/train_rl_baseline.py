"""Django management command for training and evaluating RL baseline models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core.rl.training.config import (
    RLAlgorithm,
    RLTrainingConfig,
    create_smoke_training_config,
)
from apps.core.rl.training.evaluator import RLBaselineEvaluator
from apps.core.rl.training.trainer import RLBaselineTrainer


class Command(BaseCommand):
    """Train, evaluate, and save reinforcement learning baseline policies."""

    help = (
        "Execute reproducible RL baseline training using MaskablePPO or standard PPO, "
        "save model checkpoints and artifacts, and evaluate against heuristic baselines."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--smoke",
            action="store_true",
            help="Execute a minimal, fast 64-timestep smoke training and evaluation cycle.",
        )
        parser.add_argument(
            "--train",
            action="store_true",
            help="Run full baseline training pipeline.",
        )
        parser.add_argument(
            "--eval-only",
            action="store_true",
            help="Skip training and evaluate an existing saved model artifact.",
        )
        parser.add_argument(
            "--algorithm",
            type=str,
            default="MaskablePPO",
            choices=["MaskablePPO", "PPO"],
            help="Algorithm to train: MaskablePPO (default) or standard PPO.",
        )
        parser.add_argument(
            "--scenario",
            type=str,
            default="bench_grid_sparse_3x3",
            help="Standardized scenario ID for training. Default: bench_grid_sparse_3x3.",
        )
        parser.add_argument(
            "--timesteps",
            type=int,
            default=2048,
            help="Total environment timesteps for training. Default: 2048.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Deterministic base training seed. Default: 42.",
        )
        parser.add_argument(
            "--eval-seeds",
            type=str,
            default="101,102,103,104,105",
            help="Comma-separated integer seeds for held-out evaluation.",
        )
        parser.add_argument(
            "--eval-scenarios",
            type=str,
            default="bench_grid_sparse_3x3,bench_incident_closure",
            help="Comma-separated scenario IDs for held-out evaluation.",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="artifacts/rl_models",
            help="Directory to save model artifacts and evaluation reports.",
        )
        parser.add_argument(
            "--run-name",
            type=str,
            default=None,
            help="Identifier for the run and subfolder name.",
        )
        parser.add_argument(
            "--model-path",
            type=str,
            default=None,
            help="Path to an existing model .zip artifact for evaluation or resume.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        smoke = options.get("smoke", False)
        train = options.get("train", False)
        eval_only = options.get("eval_only", False)

        # Default action: if neither train, eval_only, nor smoke is passed, run train + eval
        if not smoke and not train and not eval_only:
            train = True

        if smoke:
            self._handle_smoke(options)
            return

        if eval_only:
            self._handle_eval_only(options)
            return

        self._handle_full_train(options)

    def _handle_smoke(self, options: Any) -> None:
        """Execute fast, bounded smoke verification for CI and debugging."""
        self.stdout.write(
            self.style.NOTICE(">>> Starting RL Baseline Smoke Training Verification...")
        )

        output_dir = options.get("output_dir") or "artifacts/rl_models"
        algorithm = RLAlgorithm(options.get("algorithm", "MaskablePPO"))
        seed = int(options.get("seed", 42))

        config = create_smoke_training_config(
            run_name="smoke_training_run",
            output_dir=output_dir,
            algorithm=algorithm,
            seed=seed,
        )

        trainer = RLBaselineTrainer(config)
        train_result = trainer.train()

        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] Smoke training completed in {train_result.elapsed_time_s:.2f}s "
                f"({train_result.total_timesteps} steps)."
            )
        )
        self.stdout.write(f"Saved model: {train_result.model_path}")
        self.stdout.write(f"Metadata: {train_result.metadata_path}")

        # Verify model reload and inference
        self.stdout.write(">>> Verifying model artifact reload and held-out evaluation...")
        evaluator = RLBaselineEvaluator(config)
        report = evaluator.evaluate(
            trained_policy=train_result.model_path,
            eval_seeds=[seed + 100],
            eval_scenarios=["bench_grid_sparse_3x3"],
            save_report=True,
        )

        self.stdout.write(self.style.SUCCESS("[OK] Smoke evaluation completed."))
        self.stdout.write(report.to_markdown())
        self.stdout.write(
            self.style.SUCCESS(">>> RL Baseline Training Smoke Verification: ALL GATES PASSED")
        )

    def _handle_eval_only(self, options: Any) -> None:
        model_path = options.get("model_path")
        if not model_path:
            raise CommandError("--model-path is required when using --eval-only.")

        path = Path(model_path)
        if not path.is_file():
            raise CommandError(f"Model file not found: {path.resolve()}")

        eval_seeds = [int(s.strip()) for s in options.get("eval_seeds", "").split(",") if s.strip()]
        eval_scenarios = [
            s.strip() for s in options.get("eval_scenarios", "").split(",") if s.strip()
        ]
        algorithm = RLAlgorithm(options.get("algorithm", "MaskablePPO"))
        output_dir = options.get("output_dir") or "artifacts/rl_models"
        run_name = options.get("run_name") or "eval_existing_model"

        config = RLTrainingConfig(
            run_name=run_name,
            algorithm=algorithm,
            eval_seeds=eval_seeds,
            eval_scenarios=eval_scenarios,
            output_dir=output_dir,
        )

        self.stdout.write(self.style.NOTICE(f">>> Evaluating model from: {path}"))
        evaluator = RLBaselineEvaluator(config)
        report = evaluator.evaluate(
            trained_policy=str(path),
            eval_seeds=eval_seeds,
            eval_scenarios=eval_scenarios,
            save_report=True,
        )

        self.stdout.write(self.style.SUCCESS("[OK] Evaluation complete."))
        self.stdout.write(report.to_markdown())

    def _handle_full_train(self, options: Any) -> None:
        algorithm = RLAlgorithm(options.get("algorithm", "MaskablePPO"))
        scenario_id = options.get("scenario", "bench_grid_sparse_3x3")
        timesteps = int(options.get("timesteps", 2048))
        seed = int(options.get("seed", 42))
        output_dir = options.get("output_dir") or "artifacts/rl_models"
        run_name = options.get("run_name") or f"{algorithm.value.lower()}_{scenario_id}_s{seed}"

        eval_seeds = [int(s.strip()) for s in options.get("eval_seeds", "").split(",") if s.strip()]
        eval_scenarios = [
            s.strip() for s in options.get("eval_scenarios", "").split(",") if s.strip()
        ]

        config = RLTrainingConfig(
            run_name=run_name,
            algorithm=algorithm,
            scenario_id=scenario_id,
            train_seed=seed,
            eval_seeds=eval_seeds,
            eval_scenarios=eval_scenarios,
            total_timesteps=timesteps,
            output_dir=output_dir,
            checkpoint_freq=1024,
            verbose=1,
        )

        self.stdout.write(
            self.style.NOTICE(
                f">>> Initiating RL Baseline Training [{algorithm.value}] on '{scenario_id}' "
                f"({timesteps} timesteps, seed {seed})..."
            )
        )

        trainer = RLBaselineTrainer(config)
        train_result = trainer.train()

        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] Training complete in {train_result.elapsed_time_s:.2f}s! "
                f"Final model: {train_result.model_path}"
            )
        )

        # Run held-out evaluation
        self.stdout.write(
            ">>> Running post-training evaluation across held-out scenarios and seeds..."
        )
        evaluator = RLBaselineEvaluator(config)
        report = evaluator.evaluate(
            trained_policy=train_result.model_path,
            eval_seeds=eval_seeds,
            eval_scenarios=eval_scenarios,
            save_report=True,
        )

        self.stdout.write(self.style.SUCCESS("[OK] Evaluation complete. Summary:"))
        self.stdout.write(report.to_markdown())
