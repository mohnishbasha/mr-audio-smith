{{- define "mr-audio-smith.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "mr-audio-smith.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "mr-audio-smith.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels. Call with (dict "ctx" . "component" "api"). */}}
{{- define "mr-audio-smith.labels" -}}
helm.sh/chart: {{ include "mr-audio-smith.chart" .ctx }}
{{ include "mr-audio-smith.selectorLabels" . }}
app.kubernetes.io/version: {{ .ctx.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
{{- end }}

{{- define "mr-audio-smith.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mr-audio-smith.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "mr-audio-smith.image" -}}
{{- printf "%s:%s%s" .Values.image.repository (toString (default .Chart.AppVersion .Values.image.tag)) .Values.image.variant }}
{{- end }}

{{- define "mr-audio-smith.secretName" -}}
{{- default (include "mr-audio-smith.fullname" .) .Values.auth.existingSecret }}
{{- end }}

{{- define "mr-audio-smith.mayaEnabled" -}}
{{- if and .Values.maya2.enabled (not .Values.maya2.externalUrl) }}true{{ end }}
{{- end }}

{{- define "mr-audio-smith.ollamaEnabled" -}}
{{- if and .Values.ollama.enabled (not .Values.ollama.externalHost) (not .Values.vllm.enabled) }}true{{ end }}
{{- end }}

{{- define "mr-audio-smith.mayaUrl" -}}
{{- if .Values.maya2.externalUrl }}{{ .Values.maya2.externalUrl }}
{{- else if .Values.maya2.enabled }}http://{{ include "mr-audio-smith.fullname" . }}-maya2:8080/v1{{ end }}
{{- end }}

{{- define "mr-audio-smith.ollamaHost" -}}
{{- if .Values.ollama.externalHost }}{{ .Values.ollama.externalHost }}
{{- else }}http://{{ include "mr-audio-smith.fullname" . }}-ollama:11434{{ end }}
{{- end }}

{{- define "mr-audio-smith.backend" -}}
{{- if .Values.config.defaultBackend }}{{ .Values.config.defaultBackend }}
{{- else if include "mr-audio-smith.mayaUrl" . }}maya2
{{- else }}kokoro{{ end }}
{{- end }}

{{- define "mr-audio-smith.llm" -}}
{{- if .Values.config.llm }}{{ .Values.config.llm }}
{{- else if .Values.vllm.enabled }}openai_compat:http://{{ include "mr-audio-smith.fullname" . }}-vllm:8000/v1#{{ .Values.vllm.model }}
{{- else }}ollama:{{ .Values.ollama.model }}{{ end }}
{{- end }}

{{/* RWX for the shared cache when more than one replica can run. */}}
{{- define "mr-audio-smith.cacheAccessMode" -}}
{{- if .Values.persistence.cache.accessMode }}{{ .Values.persistence.cache.accessMode }}
{{- else if or (gt (int .Values.replicaCount) 1) (and .Values.autoscaling.enabled (gt (int .Values.autoscaling.maxReplicas) 1)) }}ReadWriteMany
{{- else }}ReadWriteOnce{{ end }}
{{- end }}

{{/* PVC claim name for a persistence block. Call with (dict "ctx" . "key" "cache"). */}}
{{- define "mr-audio-smith.claimName" -}}
{{- $p := index .ctx.Values.persistence .key -}}
{{- default (printf "%s-%s" (include "mr-audio-smith.fullname" .ctx) .key) $p.existingClaim }}
{{- end }}
