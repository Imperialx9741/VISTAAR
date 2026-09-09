import { apiGet, apiPost } from "./client";
import type {
  Broadcast,
  CreateBroadcastRequest,
  CreateTemplateRequest,
  Delivery,
  NotificationTemplate,
  PaginatedEnvelope,
} from "./types";

/**
 * Notifications (api-contracts.md §46.10 history, §46.13 templates,
 * §46.21 broadcasts, ADR-0044, ADR-0055, Admin Web §4.12). No
 * sample-data fallback, same rule as every other operational screen in
 * this app.
 */

export function searchDeliveries(
  channel: string,
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<Delivery>> {
  return apiGet<PaginatedEnvelope<Delivery>>(
    "/api/v1/admin/notifications/deliveries",
    {
      channel: channel || undefined,
      status: status || undefined,
      page,
      page_size: pageSize,
    },
  );
}

export function listTemplates(
  templateKey: string,
  channel: string,
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<NotificationTemplate>> {
  return apiGet<PaginatedEnvelope<NotificationTemplate>>(
    "/api/v1/admin/notifications/templates",
    {
      template_key: templateKey || undefined,
      channel: channel || undefined,
      status: status || undefined,
      page,
      page_size: pageSize,
    },
  );
}

export function getTemplate(templateId: string): Promise<NotificationTemplate> {
  return apiGet<NotificationTemplate>(
    `/api/v1/admin/notifications/templates/${templateId}`,
  );
}

export function createTemplate(
  body: CreateTemplateRequest,
): Promise<NotificationTemplate> {
  return apiPost<NotificationTemplate>(
    "/api/v1/admin/notifications/templates",
    body,
  );
}

export function publishTemplate(
  templateId: string,
): Promise<NotificationTemplate> {
  return apiPost<NotificationTemplate>(
    `/api/v1/admin/notifications/templates/${templateId}/publish`,
    {},
  );
}

export function createBroadcast(
  body: CreateBroadcastRequest,
): Promise<Broadcast> {
  return apiPost<Broadcast>("/api/v1/admin/notifications/broadcasts", body);
}

export function searchBroadcasts(
  status: string,
  page: number,
  pageSize: number,
): Promise<PaginatedEnvelope<Broadcast>> {
  return apiGet<PaginatedEnvelope<Broadcast>>(
    "/api/v1/admin/notifications/broadcasts",
    {
      status: status || undefined,
      page,
      page_size: pageSize,
    },
  );
}

export function getBroadcast(broadcastId: string): Promise<Broadcast> {
  return apiGet<Broadcast>(
    `/api/v1/admin/notifications/broadcasts/${broadcastId}`,
  );
}
