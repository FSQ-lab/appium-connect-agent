"""Public synchronous local diagnostics and external connection scopes."""

from appium_connect_agent.contracts import LocalSettings as LocalSettings

from ._connection import RuntimeConnection as RuntimeConnection
from ._diagnostics import Runtime as Runtime
from ._installation import supported_combinations as supported_combinations
from ._models import (
    DiagnosticCheck as DiagnosticCheck,
)
from ._models import (
    DiagnosticReport as DiagnosticReport,
)
from ._models import (
    EnvironmentBusyError as EnvironmentBusyError,
)
from ._models import (
    InstallationCombination as InstallationCombination,
)
from ._models import (
    InstallationComponent as InstallationComponent,
)
from ._models import (
    InstallationError as InstallationError,
)
from ._models import (
    InstallationResult as InstallationResult,
)
from ._models import (
    InstallRequest as InstallRequest,
)
from ._models import (
    InvalidStateError as InvalidStateError,
)
from ._models import (
    OperationCancelledError as OperationCancelledError,
)
from ._models import (
    OperationControl as OperationControl,
)
from ._models import (
    OperationTimeoutError as OperationTimeoutError,
)
from ._models import (
    ProgressEvent as ProgressEvent,
)
from ._models import (
    RuntimeOperationError as RuntimeOperationError,
)
from ._models import (
    ServiceConnectionError as ServiceConnectionError,
)
from ._models import (
    UnsupportedVersionError as UnsupportedVersionError,
)
