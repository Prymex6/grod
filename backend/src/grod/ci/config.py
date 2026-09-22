"""Reading the pipeline description a project keeps in its repository.

The file lives at `.grod/ci.yml` and looks like this:

    stages: [build, test]
    variables:
      COLOUR: red
    jobs:
      build:
        stage: build
        script:
          - echo "building"
      test:
        stage: test
        image: python:3.14
        script: pytest
"""

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

CONFIG_PATH = ".grod/ci.yml"
DEFAULT_STAGE = "build"
NAME_MAX_LENGTH = 100
MAX_JOBS = 50
MAX_SCRIPT_LINES = 200


class ConfigError(Exception):
    """The file is there but the platform cannot make sense of it."""


class JobConfig(BaseModel):
    """One job: a list of shell lines run in order."""

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(default=DEFAULT_STAGE, min_length=1, max_length=NAME_MAX_LENGTH)
    # Empty means the runner picks: its own shell, or its default image.
    image: str | None = Field(default=None, max_length=200)
    script: list[str] = Field(min_length=1, max_length=MAX_SCRIPT_LINES)
    variables: dict[str, str] = Field(default_factory=dict)

    @field_validator("script", mode="before")
    @classmethod
    def _one_line_is_a_script(cls, value: object) -> object:
        """A single line may be written without a list, as everybody expects."""
        return [value] if isinstance(value, str) else value


class PipelineConfig(BaseModel):
    """The whole file: the order of the stages and the jobs to run."""

    model_config = ConfigDict(extra="forbid")

    stages: list[str] = Field(default_factory=lambda: [DEFAULT_STAGE], max_length=20)
    variables: dict[str, str] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(min_length=1, max_length=MAX_JOBS)

    def ordered_jobs(self) -> list[tuple[str, JobConfig]]:
        """Return the jobs in the order their stages run, then by name."""
        return sorted(
            self.jobs.items(),
            key=lambda item: (self.stages.index(item[1].stage), item[0]),
        )


def parse(text: str) -> PipelineConfig:
    """Turn the contents of the file into a checked description."""
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"The file is not valid YAML: {error}") from error

    if not isinstance(loaded, dict):
        raise ConfigError("The file must describe stages and jobs")

    try:
        config = PipelineConfig.model_validate(loaded)
    except ValueError as error:
        raise ConfigError(str(error)) from error

    unknown = {job.stage for job in config.jobs.values()} - set(config.stages)
    if unknown:
        raise ConfigError(f"These stages are used but not declared: {', '.join(sorted(unknown))}")
    return config
