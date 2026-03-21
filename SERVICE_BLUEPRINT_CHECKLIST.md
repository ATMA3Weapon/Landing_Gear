# Service Blueprint Checklist

Before building out a new service:

- rename the service package and service metadata
- keep `landing_gear/` generic
- create at least one small core module
- keep repositories in the service package, not in the kernel
- run `python install.py doctor`
- run `python install.py readiness`
- run `python install.py smoke`
- run `python install.py run`

This starter intentionally keeps the example small so the reusable pattern stays obvious.
