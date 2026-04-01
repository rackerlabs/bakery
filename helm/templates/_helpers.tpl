{{- define "bakery.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "bakery.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "bakery.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "bakery.uiFullname" -}}
{{- printf "%s-ui" (include "bakery.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "bakery.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "bakery.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "bakery.selectorLabels" -}}
app.kubernetes.io/name: {{ include "bakery.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "bakery.serviceAccountName" -}}
{{- $serviceAccount := .Values.bakery.serviceAccount | default dict -}}
{{- $name := $serviceAccount.name | default "" -}}
{{- $create := $serviceAccount.create | default true -}}
{{- if $create -}}
{{- default (include "bakery.fullname" .) $name -}}
{{- else -}}
{{- default "default" $name -}}
{{- end -}}
{{- end -}}

{{- define "bakery.secretName" -}}
{{- printf "%s-secret" (include "bakery.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "bakery.gatewayManagerName" -}}
{{- printf "%s-%s-gateway-manager" .Release.Namespace (include "bakery.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "bakery.dbHost" -}}
{{- $database := .Values.bakery.database | default dict -}}
{{- $host := $database.host | default "" -}}
{{- if $host -}}
{{- $host -}}
{{- else -}}
{{- printf "%s-mariadb" (include "bakery.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "bakery.dbSecretName" -}}
{{- if .Values.bakery.database.user.passwordSecret -}}
{{- .Values.bakery.database.user.passwordSecret -}}
{{- else -}}
{{- printf "%s-db-user" (include "bakery.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "bakery.dbSecretKey" -}}
{{- .Values.bakery.database.user.passwordSecretKey | default "password" -}}
{{- end -}}

{{- define "bakery.imageVersion" -}}
{{- if .Values.bakery.image.tag -}}
{{- .Values.bakery.image.tag -}}
{{- else -}}
{{- .Chart.AppVersion -}}
{{- end -}}
{{- end -}}

{{- define "bakery.imageRef" -}}
{{- $repo := .Values.bakery.image.repository -}}
{{- $digest := .Values.bakery.image.digest | default "" -}}
{{- if $digest -}}
{{ printf "%s@%s" $repo $digest }}
{{- else -}}
{{ printf "%s:%s" $repo (include "bakery.imageVersion" .) }}
{{- end -}}
{{- end -}}

{{- define "bakery.uiImageVersion" -}}
{{- if .Values.bakery.ui.image.tag -}}
{{- .Values.bakery.ui.image.tag -}}
{{- else -}}
{{- .Chart.AppVersion -}}
{{- end -}}
{{- end -}}

{{- define "bakery.uiImageRef" -}}
{{- $repo := .Values.bakery.ui.image.repository -}}
{{- $digest := .Values.bakery.ui.image.digest | default "" -}}
{{- if $digest -}}
{{ printf "%s@%s" $repo $digest }}
{{- else -}}
{{ printf "%s:%s" $repo (include "bakery.uiImageVersion" .) }}
{{- end -}}
{{- end -}}

{{- define "bakery.pullSecrets" -}}
{{- $pullSecrets := .Values.bakery.image.pullSecrets | default list -}}
{{- if gt (len $pullSecrets) 0 }}
imagePullSecrets:
{{- range $secret := $pullSecrets }}
  {{- if kindIs "string" $secret }}
  - name: {{ $secret | quote }}
  {{- else if and (kindIs "map" $secret) (hasKey $secret "name") }}
  - name: {{ index $secret "name" | quote }}
  {{- end }}
{{- end }}
{{- end }}
{{- end -}}

{{- define "bakery.waitForDbInitContainer" -}}
- name: wait-for-db
  image: {{ .Values.images.busybox | quote }}
  securityContext:
    {{- toYaml .Values.utilitySecurityContext | nindent 4 }}
  command:
    - sh
    - -c
    - |
      until nc -z -v -w30 {{ include "bakery.dbHost" . }} 3306; do
        echo "Waiting for MariaDB..."
        sleep 5
      done
      echo "MariaDB is ready"
{{- end -}}

{{- define "bakery.logGroupLabel" -}}
bakery.rackerlabs.com/log-group: "bakery"
{{- end -}}

{{- define "bakery.logRoleApi" -}}
bakery.rackerlabs.com/log-subgroup: "app"
bakery.rackerlabs.com/log-role: "api"
{{- end -}}

{{- define "bakery.logRoleWorker" -}}
bakery.rackerlabs.com/log-subgroup: "app"
bakery.rackerlabs.com/log-role: "worker"
{{- end -}}

{{- define "bakery.logRoleUi" -}}
bakery.rackerlabs.com/log-subgroup: "app"
bakery.rackerlabs.com/log-role: "ui"
{{- end -}}

{{- define "bakery.logRoleInfra" -}}
bakery.rackerlabs.com/log-subgroup: "data"
bakery.rackerlabs.com/log-role: "infra"
{{- end -}}

{{- define "bakery.podPlacement" -}}
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}
