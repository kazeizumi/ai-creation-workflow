# Runtime selection

Choose local when the workflow and models are already available, privacy or
iteration control matters, and local turnaround is acceptable. Choose cloud
when local VRAM, model availability, queue stability or deadline makes the
remote instance more useful.

Compare:

- measured end-to-end minutes per successful clip;
- rental rate and minimum billing unit;
- upload and startup overhead;
- retry probability and who owns shutdown;
- workflow parity and reproducibility;
- privacy and license constraints.

If the cost ranges overlap, prefer the backend with better turnaround and lower
failure risk for urgent or batch work. Prefer the cheaper measured backend for
non-urgent single clips when its success rate is comparable.
