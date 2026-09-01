/**
 * The product's navigation model.
 *
 * The shell used to expose every subsystem as an equal top-level button, so
 * "Chat" and "Logs" read as peers. They are not. Destinations belong to one
 * of four pillars, and the header renders those pillars as labelled groups.
 *
 * This module is the single definition of what destinations exist, what they
 * are called, which pillar owns them, and which roles may see them. The shell
 * (TabbedPageLayout) and the header both read it, so a destination cannot be
 * navigable but invisible, or listed but unreachable.
 */

import {
  BarChart3,
  Brain,
  Cpu,
  FlaskConical,
  HeartPulse,
  Library,
  MessageSquare,
  Settings2,
  Terminal,
  Upload,
  Users,
  Zap,
} from 'lucide-react'
import { PRODUCT_LABEL_KEYS } from '@/lib/terminology'

export const NAV_PILLARS = Object.freeze({
  WORKSPACE: 'workspace',
  QUALITY: 'quality',
  OPERATIONS: 'operations',
  ADMINISTRATION: 'administration',
})

/**
 * Pillar → translation key.
 *
 * This module is imported by the shell's route resolution as well as by the
 * header, so it must stay free of React hooks: it carries keys, and whichever
 * component renders a pillar resolves the key against the active locale.
 */
export const PILLAR_LABEL_KEYS = Object.freeze({
  [NAV_PILLARS.WORKSPACE]: 'nav.pillar.workspace',
  [NAV_PILLARS.QUALITY]: 'nav.pillar.quality',
  [NAV_PILLARS.OPERATIONS]: 'nav.pillar.operations',
  [NAV_PILLARS.ADMINISTRATION]: 'nav.pillar.administration',
})

/**
 * Pillar order is the reading order of the header — left to right in English,
 * right to left in Hebrew, which CSS direction produces from this one order.
 * The array is never reversed for RTL; doing so would mirror it twice.
 */
export const PILLAR_ORDER = Object.freeze([
  NAV_PILLARS.WORKSPACE,
  NAV_PILLARS.QUALITY,
  NAV_PILLARS.OPERATIONS,
  NAV_PILLARS.ADMINISTRATION,
])

/**
 * Roles, and the pillars each one may see.
 *
 * The gateway currently issues exactly two roles (`admin` and `user`; see
 * `backend/gateway/app/schemas/auth.py`). The intermediate tiers are listed
 * because the product model calls for them and because a role the backend
 * starts issuing must not silently fall through to "sees nothing" — but no
 * tier here grants anything the server does not already allow. This table
 * decides what is *shown*; authorization stays server-side, and every
 * destination still calls an endpoint that checks it again.
 */
export const ROLE_PILLARS = Object.freeze({
  user: [NAV_PILLARS.WORKSPACE],
  member: [NAV_PILLARS.WORKSPACE],
  evaluator: [NAV_PILLARS.WORKSPACE, NAV_PILLARS.QUALITY],
  operator: [NAV_PILLARS.WORKSPACE, NAV_PILLARS.QUALITY, NAV_PILLARS.OPERATIONS],
  admin: PILLAR_ORDER,
})

const DEFAULT_ROLE = 'user'

/**
 * Every destination the shell can render.
 *
 * `roles` is an allow-list rather than an `adminOnly` flag so that a
 * member-only destination (Upload, the contribution path for people who
 * cannot manage the whole library) is expressible in the same table.
 *
 * `feature` marks destinations whose flag decides whether they exist at all.
 */
export const DESTINATIONS = Object.freeze([
  {
    id: 'chat',
    labelKey: PRODUCT_LABEL_KEYS.chat,
    icon: MessageSquare,
    pillar: NAV_PILLARS.WORKSPACE,
    roles: ['admin', 'operator', 'evaluator', 'member', 'user'],
  },
  {
    id: 'files',
    labelKey: PRODUCT_LABEL_KEYS.knowledge,
    icon: Library,
    pillar: NAV_PILLARS.WORKSPACE,
    roles: ['admin', 'operator', 'evaluator'],
  },
  {
    id: 'upload',
    labelKey: PRODUCT_LABEL_KEYS.upload,
    icon: Upload,
    pillar: NAV_PILLARS.WORKSPACE,
    roles: ['member', 'user'],
  },
  {
    id: 'memory',
    labelKey: PRODUCT_LABEL_KEYS.memory,
    icon: Brain,
    pillar: NAV_PILLARS.WORKSPACE,
    roles: ['admin', 'operator', 'evaluator', 'member', 'user'],
  },
  {
    id: 'eval',
    labelKey: PRODUCT_LABEL_KEYS.eval,
    icon: FlaskConical,
    pillar: NAV_PILLARS.QUALITY,
    roles: ['admin', 'operator', 'evaluator'],
  },
  {
    id: 'metrics',
    labelKey: PRODUCT_LABEL_KEYS.metrics,
    icon: BarChart3,
    pillar: NAV_PILLARS.QUALITY,
    roles: ['admin', 'operator', 'evaluator'],
  },
  {
    id: 'models',
    labelKey: PRODUCT_LABEL_KEYS.models,
    icon: Cpu,
    pillar: NAV_PILLARS.OPERATIONS,
    roles: ['admin', 'operator'],
  },
  {
    id: 'logs',
    labelKey: PRODUCT_LABEL_KEYS.logs,
    icon: Terminal,
    pillar: NAV_PILLARS.OPERATIONS,
    roles: ['admin', 'operator'],
  },
  {
    id: 'health',
    labelKey: PRODUCT_LABEL_KEYS.health,
    icon: HeartPulse,
    pillar: NAV_PILLARS.OPERATIONS,
    roles: ['admin', 'operator'],
  },
  {
    id: 'training',
    labelKey: PRODUCT_LABEL_KEYS.training,
    icon: Zap,
    pillar: NAV_PILLARS.OPERATIONS,
    roles: ['admin', 'operator'],
    feature: 'training',
  },
  {
    id: 'users',
    labelKey: PRODUCT_LABEL_KEYS.users,
    icon: Users,
    pillar: NAV_PILLARS.ADMINISTRATION,
    roles: ['admin'],
  },
  {
    id: 'config',
    labelKey: PRODUCT_LABEL_KEYS.settings,
    icon: Settings2,
    pillar: NAV_PILLARS.ADMINISTRATION,
    roles: ['admin'],
  },
])

/** The destination the shell falls back to when a request is not permitted. */
export const FALLBACK_TAB = 'chat'

function normalizeRole(role) {
  const key = String(role || '').toLowerCase()
  return ROLE_PILLARS[key] ? key : DEFAULT_ROLE
}

/**
 * @param {string} role
 * @param {{features?: Record<string, boolean>}} [options]
 * @returns {Array<{id: string, labelKey: string, icon: Function, pillar: string}>}
 *   every destination this role may see, in pillar order.
 */
export function destinationsForRole(role, { features = {} } = {}) {
  const key = normalizeRole(role)
  const pillars = new Set(ROLE_PILLARS[key])
  return DESTINATIONS.filter(
    (destination) =>
      pillars.has(destination.pillar) &&
      destination.roles.includes(key) &&
      (!destination.feature || features[destination.feature] === true)
  )
}

/**
 * The same destinations, grouped for rendering.
 *
 * Empty pillars are dropped rather than rendered as a headed group with
 * nothing under it.
 *
 * @returns {Array<{pillar: string, labelKey: string, items: Array<Object>}>}
 */
export function navigationForRole(role, options) {
  const destinations = destinationsForRole(role, options)
  return PILLAR_ORDER.map((pillar) => ({
    pillar,
    labelKey: PILLAR_LABEL_KEYS[pillar],
    items: destinations.filter((destination) => destination.pillar === pillar),
  })).filter((group) => group.items.length > 0)
}

/**
 * The tab ids a role may open.
 *
 * The shell resolves a requested tab against this, so a destination removed
 * from the model becomes unreachable everywhere at once.
 */
export function allowedTabsForRole(role, options) {
  return new Set(destinationsForRole(role, options).map((destination) => destination.id))
}

/** @returns {?Object} the destination record, whatever pillar it is in. */
export function destinationById(id) {
  return DESTINATIONS.find((destination) => destination.id === id) || null
}

/**
 * The translation key that names a destination, for headings and status text.
 *
 * Returns the raw id when the destination is unknown, so a caller renders
 * something recognisable rather than nothing.
 */
export function destinationLabelKey(id) {
  return destinationById(id)?.labelKey || id
}
