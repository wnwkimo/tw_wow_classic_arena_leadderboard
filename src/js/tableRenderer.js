// tableRenderer.js - DataTable rendering and modal binding
import { escapeHtml, safeNum } from './utils.js';
import { CLASS_MAP, CLASS_COLOR_MAP, CLASS_ICON_MAP, RACE_MAP, RACE_ICON_MAP } from './constants.js';

let dataTable = null;
let currentVisible = [];

export function renderTable(list, season = 0) {
  // Store list for modal lookup
  currentVisible = list;

  // Destroy existing table if any
  if ($.fn.DataTable.isDataTable('#leaderboard')) {
    try { $('#leaderboard').DataTable().clear().destroy(); } catch(e) { console.warn(e); }
  }
  const tbody = $('#leaderboard tbody').empty();

  list.forEach((item, idx) => {
    const name = item.isTeam ? (item.teamName || '-') : (item.charName || '-');
    const realm = item.isTeam ? (item.teamRealm || '-') : (item.charRealm || '-');

    // Character/Team name with class color
    let nameHtml = escapeHtml(name);
    const classId = !item.isTeam ? item.charClassId : null;
    if (classId && CLASS_COLOR_MAP[classId]) {
      nameHtml = `<a class="name-link text-decoration-none" data-uid="${item.uid}"><span style="color:${CLASS_COLOR_MAP[classId]}">${escapeHtml(name)}</span></a>`;
    } else {
      nameHtml = `<a class="name-link text-decoration-none" data-uid="${item.uid}">${escapeHtml(name)}</a>`;
    }

    const memberNamesForSearch = item.memberNames.join(' ');

    // Class & Race columns
    let classHtml = '-';
    let raceHtml = '-';
    if (!item.isTeam) {
      if (item.charClassId) {
        const className = CLASS_MAP[item.charClassId] || item.charClassName || 'Unknown';
        const classIcon = CLASS_ICON_MAP[item.charClassId] || '';
        const classColor = CLASS_COLOR_MAP[item.charClassId] || '#FFFFFF';
        classHtml = `<div class="d-flex align-items-center class-race-container"><span style="color:${classColor}">${escapeHtml(className)}</span>${classIcon ? `<img src="${classIcon}" alt="${className}" style="width:20px;height:20px;margin-left:5px;">` : ''}</div>`;
      } else {
        classHtml = '<span class="text-muted">Unknown</span>';
      }
      if (item.charRaceId) {
        const raceName = RACE_MAP[item.charRaceId] || item.charRaceName || 'Unknown';
        const raceIcon = RACE_ICON_MAP[item.charRaceId] || '';
        raceHtml = `<div class="d-flex align-items-center class-race-container"><span>${escapeHtml(raceName)}</span>${raceIcon ? `<img src="${raceIcon}" alt="${raceName}" style="width:20px;height:20px;margin-left:5px;">` : ''}</div>`;
      } else {
        raceHtml = '<span class="text-muted">Unknown</span>';
      }
    } else {
      classHtml = '<span class="text-muted">-</span>';
      raceHtml = '<span class="text-muted">-</span>';
    }

    // Build table row
    const tr = $(`<tr data-uid="${item.uid}">
      <td>${item.rank ?? ''}</td>
      <td>${nameHtml}</td>
      <td>${escapeHtml(realm)}</td>
      <td>${classHtml}</td>
      <td>${raceHtml}</td>
      <td>${item.rating}</td>
      <td>${item.played}</td>
      <td>${item.won}</td>
      <td>${item.lost}</td>
      <td>${item.winRate.toFixed(1)}</td>
      <td class="member-names-hidden">${escapeHtml(memberNamesForSearch)}</td>
    </tr>`);

    tbody.append(tr);
  });

  // Initialize DataTable
  try {
    dataTable = $('#leaderboard').DataTable({
      pageLength: 15,
      order: [[5, 'desc']],
      columnDefs: [{ targets: 10, visible: false, searchable: true }],
      search: { smart: false },
      initComplete: function () {
        // Add class filter (season >= 5)
        if (season >= 5) {
          $('#classFilter').remove();
          let classFilter = $(`
            <select id="classFilter" class="form-select form-select-sm ms-2 w-auto">
              <option value="">All Classes</option>
            </select>
          `);
          
          // Class options with color
          Object.entries(CLASS_MAP).forEach(([id, name]) => {
            const color = CLASS_COLOR_MAP[id] || '#FFFFFF';
            classFilter.append(`<option value="${name}" style="color:${color};">${name}</option>`);
          });
          classFilter.append('<option value="Unknown">Unknown</option>');
        
          // Insert into filter area
          $('#leaderboard_filter').append(
            $('<div class="filter-controls d-flex flex-column align-items-end gap-2"></div>')
              .append(classFilter)
          );
          
          // Filter logic
          classFilter.on('change', function () {
            let val = $.fn.dataTable.util.escapeRegex($(this).val());
            dataTable.column(3).search(val ? val : '', true, false).draw();
          });
        }
      }
    });
  } catch (e) {
    console.warn('DataTable init failed', e);
  }

  // Row click → open modal
  $('#leaderboard tbody').off('click', '.name-link').on('click', '.name-link', function(ev){
    const uid = $(this).data('uid');
    const entry = currentVisible.find(x => x.uid === uid);
    if (entry) openModalFor(entry);
  });
}

export function clearTable() {
  if ($.fn.DataTable.isDataTable('#leaderboard')) {
    try { $('#leaderboard').DataTable().clear().destroy(); } catch(e) {}
  }
  $('#leaderboard tbody').empty();
}


function openModalFor(entry) {
  // Modal title & subtitle
  $('#modalTitle').text(entry.isTeam ? (entry.teamName || 'Team') : (entry.charName || 'Character'));
  $('#modalSub').text(entry.isTeam ? `Realm: ${entry.teamRealm || '-'}  •  Rating: ${entry.rating}` : `Realm: ${entry.charRealm || '-'}  •  Rating: ${entry.rating}`);

  // Crest background
  const crestEl = document.getElementById('modalCrest');
  crestEl.style.background = '#222';
  if (entry.raw.team?.crest?.background?.color?.rgba) {
    const c = entry.raw.team.crest.background.color.rgba;
    crestEl.style.background = `rgba(${c.r},${c.g},${c.b},${c.a})`;
  }

  // Member table
  const tbody = $('#memberTable tbody').empty();
  if (entry.isTeam && Array.isArray(entry.members) && entry.members.length > 0) {
    entry.members.forEach((m, idx) => {
      const ch = m.character || {};
      const name = ch.name || '-';
      const clsId = ch.playable_class?.id ?? m.character?.playable_class?.id ?? null;
      const clsName = (clsId && CLASS_MAP[clsId]) ? CLASS_MAP[clsId] : (ch.playable_class?.name || '-');
      const raceId = ch.playable_race?.id ?? null;
      const raceName = raceId ? (RACE_MAP[raceId] || `Race ${raceId}`) : '-';
      const rating = m.rating || '-';
      
      const stats = m.season_match_statistics || {};
      const played = safeNum(stats.played), won = safeNum(stats.won), lost = safeNum(stats.lost);
      const winp = played ? (won / played * 100).toFixed(1) : '0.0';
      
      // Class cell
      const classIcon = CLASS_ICON_MAP[clsId] || '';
      const classColor = CLASS_COLOR_MAP[clsId] || '#FFFFFF';
      const clsHtml = `<div class="d-flex align-items-center role-label class-race-container">
        <span style="color:${classColor}">${escapeHtml(clsName)}</span>
        ${classIcon ? `<img src="${classIcon}" alt="${clsName}" style="width:20px;height:20px;margin-left:5px;" onerror="this.style.display='none'">` : ''}
      </div>`;
      
      // Race cell
      const raceIcon = raceId ? (RACE_ICON_MAP[raceId] || '') : '';
      const raceHtml = `<div class="d-flex align-items-center class-race-container">
        <span>${escapeHtml(raceName)}</span>
        ${raceIcon ? `<img src="${raceIcon}" alt="${raceName}" style="width:20px;height:20px;margin-left:5px;" onerror="this.style.display='none'">` : ''}
      </div>`;
      
      const row = `<tr><td>${idx+1}</td><td>${escapeHtml(name)}</td><td>${clsHtml}</td><td>${raceHtml}</td><td>${rating}</td><td>${played}</td><td>${won}</td><td>${lost}</td><td>${winp}</td></tr>`;
      tbody.append(row);
    });
  } else {
    // Single character entry
    const name = entry.charName || entry.teamName || '-';
    const clsId = entry.charClassId || null;
    const clsName = (clsId && CLASS_MAP[clsId]) ? CLASS_MAP[clsId] : (entry.charClassName || '-');
    const raceId = entry.charRaceId || null;
    const raceName = raceId ? (RACE_MAP[raceId] || `Race ${raceId}`) : (entry.raw.character?.playable_race?.name || '-');
    
    const classIcon = CLASS_ICON_MAP[clsId] || '';
    const classColor = CLASS_COLOR_MAP[clsId] || '#FFFFFF';
    const clsHtml = `<div class="d-flex align-items-center role-label class-race-container">
      <span style="color:${classColor}">${escapeHtml(clsName)}</span>
      ${classIcon ? `<img src="${classIcon}" alt="${clsName}" style="width:20px;height:20px;margin-left:5px;" onerror="this.style.display='none'">` : ''}
    </div>`;
    
    const raceIcon = raceId ? (RACE_ICON_MAP[raceId] || '') : '';
    const raceHtml = `<div class="d-flex align-items-center class-race-container">
      <span>${escapeHtml(raceName)}</span>
      ${raceIcon ? `<img src="${raceIcon}" alt="${raceName}" style="width:20px;height:20px;margin-left:5px;" onerror="this.style.display='none'">` : ''}
    </div>`;
    
    const row = `<tr><td>1</td><td>${escapeHtml(name)}</td><td>${clsHtml}</td><td>${raceHtml}</td><td>${entry.rating}</td><td>${entry.played}</td><td>${entry.won}</td><td>${entry.lost}</td><td>${entry.winRate.toFixed(1)}</td></tr>`;
    tbody.append(row);
  }

  // Show modal
  const modalEl = document.getElementById('teamModal');
  const bs = new bootstrap.Modal(modalEl);
  bs.show();
}
