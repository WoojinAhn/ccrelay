# CLAUDE.md — ccrelay

## Overview

Claude Code 세션을 다른 장비에서 선택적으로 이어갈 수 있게 하는 CLI 도구.
"릴레이 경주 바통 넘기기" 메타포 — 세션 컨텍스트를 다음 장비로 넘긴다.

## Status

아이디어 단계. 브레인스토밍 완료, 구현 미착수.

## Motivation

- Claude Code 세션은 로컬(`~/.claude/`)에만 저장되어 장비 간 이동 불가
- 공식 Remote Control은 원래 장비 터미널이 켜져 있어야 함 (리모트 조종이지 세션 이동이 아님)
- claude-sync 같은 서드파티는 `~/.claude` 전체를 동기화 — 선택적 sync 불가
- **"장비 A 끄고, 장비 B에서 특정 세션만 이어가기"를 해주는 도구가 없음**

## Key Design Decisions

- **선택적 동기화**: 전체가 아닌 특정 세션만 골라서 push/pull
- **네이밍**: `cc` (Claude Code) + `relay` (릴레이 바통 넘기기). cclanes와 같은 네이밍 컨벤션.
- **언어**: Python
- **스토리지 백엔드**: Google Workspace CLI (`gws`) — Google Drive를 subprocess로 호출
- **최종 형태**: Claude Code skill/command로 래핑

## Session File Structure (참고)

- `~/.claude/transcripts/` — 세션 transcript (ses_*.jsonl)
- `~/.claude/projects/<프로젝트>/` — 프로젝트별 대화 기록 (UUID.jsonl, agent-*.jsonl)

## Existing Alternatives Investigated

| 도구 | 방식 | 한계 |
|------|------|------|
| Remote Control (공식) | 로컬 세션을 웹/앱에서 원격 조종 | 원래 장비 터미널 필수, ~10분 타임아웃, Pro/Max만 |
| claude-sync (오픈소스) | ~/.claude 전체를 R2/S3에 동기화 | 선택적 sync 불가, 클라우드 스토리지 설정 필요 |
| 수동 scp | 세션 파일 직접 복사 | 번거로움, 자동화 안 됨 |

## Principles

- cclanes와 동일: 아이디어 먼저, 충분히 구체화 후 구현
- 초기에는 가볍게. 오버엔지니어링 금지.
- Zero dependencies 지향 (cclanes 컨셉 계승). 단, gws CLI는 외부 전제조건으로 허용.
