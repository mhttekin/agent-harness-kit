"""Ground truth changes require a deliberate owner-authorized override."""

import os
import sys

if os.environ.get("ALLOW_LABEL_EDIT") != "1":
    sys.exit(
        "evals/labels is protected ground truth. Obtain owner authorization first; "
        "then use ALLOW_LABEL_EDIT=1 for that invocation only."
    )
