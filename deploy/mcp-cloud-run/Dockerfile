# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    CXIDK_TRANSCRIPT_MODE=redacted

WORKDIR /app

RUN groupadd --system --gid 10001 cxidk && \
    useradd --system --uid 10001 --gid cxidk --no-create-home cxidk

COPY pyproject.toml README.md LICENSE.txt ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[mcp,dlp,speech]"

USER cxidk

EXPOSE 8080

ENTRYPOINT ["cxidk-mcp"]
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
