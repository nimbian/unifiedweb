import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  useCharacter,
  useEquip,
  useRename,
  useRetire,
  useUnequip,
} from "../api/hooks";
import PaperDoll from "../components/PaperDoll";
import StatBlock from "../components/StatBlock";
import ConfirmDialog from "../components/ConfirmDialog";

export default function CharacterSheet() {
  const { id } = useParams();
  const charId = Number(id);
  const navigate = useNavigate();
  const character = useCharacter(charId);
  const rename = useRename(charId);
  const retire = useRetire(charId);
  const equip = useEquip(charId);
  const unequip = useUnequip(charId);

  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState("");
  const [confirmRetire, setConfirmRetire] = useState(false);

  if (character.isLoading) return <p className="muted">Loading…</p>;
  if (character.error) return <p className="error">{character.error.message}</p>;
  const ch = character.data!;
  const owner = ch.is_owner === true;
  const busy = rename.isPending || retire.isPending || equip.isPending || unequip.isPending;
  const mutationError =
    rename.error?.message ?? retire.error?.message ??
    equip.error?.message ?? unequip.error?.message;

  const bag = (ch.inventory ?? []).filter((i) => !i.equipped);

  return (
    <div>
      <div className="row">
        <h1 style={{ margin: 0 }}>
          {ch.name} <span className="muted">Lv{ch.level}</span>
        </h1>
        {ch.is_retired && <span className="pill">retired</span>}
        {owner && !ch.is_retired && (
          <button className="btn small ghost" onClick={() => {
            setNewName(ch.name);
            setRenaming(!renaming);
          }}>
            Rename
          </button>
        )}
        {owner && !ch.is_retired && (
          <button className="btn small danger" onClick={() => setConfirmRetire(true)}>
            Retire
          </button>
        )}
      </div>
      <div className="sub">
        {ch.personality && `${ch.personality} `}
        {ch.race} {ch.class_name}
        {ch.owner_login && <> · @{ch.owner_login}</>}
        {ch.lineage.trained_by && (
          <>
            {" · gen "}{ch.lineage.generation}, trained by{" "}
            {ch.lineage.trained_by.map((p, i) => (
              <span key={p.id}>
                {i > 0 && " & "}
                <Link to={`/characters/${p.id}`}>{p.name}</Link>
              </span>
            ))}
          </>
        )}
      </div>

      {renaming && (
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            rename.mutate(
              { name: newName },
              { onSuccess: () => setRenaming(false) },
            );
          }}
        >
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={20}
            autoFocus
          />
          <button className="btn small" disabled={busy}>
            Save
          </button>
        </form>
      )}
      {mutationError && <p className="error">{mutationError}</p>}

      <StatBlock stats={ch.stats} />

      <div className="card">
        <div className="row">
          <span>
            <strong>{ch.wins}</strong>W / <strong>{ch.losses}</strong>L
          </span>
          <span className="pill">{ch.battles_fought} battles fought</span>
          {!ch.is_retired && <span className="pill">{ch.battles_left} left</span>}
          <span className="pill">
            {ch.lifetime_damage.toLocaleString()} lifetime dmg
          </span>
          <span className="pill">{ch.highest_hit.toLocaleString()} biggest hit</span>
          <span className="pill">{ch.lifetime_crits.toLocaleString()} crits</span>
        </div>
      </div>

      <h2>Gear</h2>
      <PaperDoll
        equipment={ch.equipment}
        onUnequip={owner && !ch.is_retired ? (slot) => unequip.mutate({ slot }) : undefined}
        busy={busy}
      />
      {owner && bag.length > 0 && (
        <>
          <h2>Bag</h2>
          <div className="grid">
            {bag.map((item) => (
              <div className="card" key={item.item_id}>
                <h3>{item.name}</h3>
                <div className="sub">{item.slot}</div>
                {!ch.is_retired && (
                  <button
                    className="btn small"
                    onClick={() => equip.mutate({ item_id: item.item_id })}
                    disabled={busy}
                  >
                    Equip
                  </button>
                )}
              </div>
            ))}
          </div>
        </>
      )}
      {owner && !ch.is_retired && (
        <p className="muted">
          Need more gear? Visit the <Link to="/shop">shop</Link>.
        </p>
      )}

      {confirmRetire && (
        <ConfirmDialog
          title={`Retire ${ch.name}?`}
          body="Retirement is permanent — the character stops fighting and keeps its place in your retired legends (and can mentor new characters later). Gear is lost; your gold is kept."
          confirmLabel="Retire"
          busy={retire.isPending}
          onCancel={() => setConfirmRetire(false)}
          onConfirm={() =>
            retire.mutate(
              {},
              {
                onSuccess: () => {
                  setConfirmRetire(false);
                  navigate("/roster");
                },
                onError: () => setConfirmRetire(false),
              },
            )
          }
        />
      )}
    </div>
  );
}
