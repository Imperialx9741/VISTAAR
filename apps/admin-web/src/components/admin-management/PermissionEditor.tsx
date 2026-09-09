import { GRANTABLE_MODULES } from "@/lib/admin-modules";
import type { AccessLevel, AdminPermission } from "@/lib/api/types";
import styles from "./PermissionEditor.module.css";

type EditableLevel = AccessLevel | "NONE";

interface PermissionEditorProps {
  value: AdminPermission[];
  onChange: (next: AdminPermission[]) => void;
  disabled?: boolean;
}

/**
 * One row per grantable module (every AdminModule except ADMIN_MANAGEMENT
 * and SETTINGS — those are never grantable, ADR-0040/BR-126, and simply
 * don't appear here). Each row is a 3-way None/View/Manage choice,
 * matching the backend's actual AccessLevel domain exactly — there is no
 * fourth "Approve" level in this codebase. `value`/`onChange` hold only
 * the modules with a real grant, same shape the PATCH .../permissions
 * body expects (absence of a row = no access).
 */
export function PermissionEditor({
  value,
  onChange,
  disabled = false,
}: PermissionEditorProps) {
  function levelFor(module: string): EditableLevel {
    return (
      value.find((permission) => permission.module === module)
        ?.access_level ?? "NONE"
    );
  }

  function setLevel(module: AdminPermission["module"], level: EditableLevel) {
    const withoutModule = value.filter(
      (permission) => permission.module !== module,
    );
    onChange(
      level === "NONE"
        ? withoutModule
        : [...withoutModule, { module, access_level: level }],
    );
  }

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th className={styles.moduleHeader}>Module</th>
          <th>None</th>
          <th>View</th>
          <th>Manage</th>
        </tr>
      </thead>
      <tbody>
        {GRANTABLE_MODULES.map(({ module, label }) => {
          const current = levelFor(module);
          const groupName = `permission-${module}`;
          return (
            <tr key={module}>
              <td className={styles.moduleLabel}>{label}</td>
              {(["NONE", "VIEW", "MANAGE"] as const).map((level) => (
                <td key={level} className={styles.radioCell}>
                  <input
                    type="radio"
                    name={groupName}
                    disabled={disabled}
                    checked={current === level}
                    onChange={() => setLevel(module, level)}
                    aria-label={`${label} — ${level === "NONE" ? "no access" : level}`}
                  />
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
