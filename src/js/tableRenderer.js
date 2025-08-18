// tableRenderer.js - render DataTable and wire row click
import { escapeHtml, safeNum } from './utils.js';
import { CLASS_MAP, CLASS_COLOR_MAP, CLASS_ICON_MAP, RACE_MAP, RACE_ICON_MAP } from './constants.js';

let dataTable = null;
let currentVisible = [];

export function renderTable(list, season = 0) {
  // Store the list for the modal function
  currentVisible = list;

  // destroy existing table before modifying DOM
  if ($.fn.DataTable.isDataTable('#leaderboard')) {
    try{ $('#leaderboard').DataTable().clear().destroy(); }catch(e){ console.warn(e); }
  }
  const tbody = $('#leaderboard tbody').empty();

  list.forEach((item, idx)=>{
    const name = item.isTeam ? (item.teamName || '-') : (item.charName || '-');
    const realm = item.isTeam ? (item.teamRealm || '-') : (item.charRealm || '-');

    let nameHtml = escapeHtml(name);
    const classId = !item.isTeam ? item.charClassId : null;
    if (classId && CLASS_COLOR_MAP[classId]){
      nameHtml = `<a class="name-link text-decoration-none" data-uid="${item.uid}"><span style="color:${CLASS_COLOR_MAP[classId]}">${escapeHtml(name)}</span></a>`;
    } else {
      nameHtml = `<a class="name-link text-decoration-none" data-uid="${item.uid}">${escapeHtml(name)}</a>`;
    }

    const memberNamesForSearch = item.memberNames.join(' ');

    let classHtml = '-';
    let raceHtml = '-';
    if (!item.isTeam) {
      if (item.charClassId) {
        const className = CLASS_MAP[item.charClassId] || item.charClassName || '未知';
        const classIcon = CLASS_ICON_MAP[item.charClassId] || '';
        const classColor = CLASS_COLOR_MAP[item.charClassId] || '#FFFFFF';
        classHtml = `<div class="d-flex align-items-center class-race-container"><span style="color:${classColor}">${escapeHtml(className)}</span>${classIcon ? `<img src="${classIcon}" alt="${className}" style="width:20px;height:20px;margin-left:5px;">` : ''}</div>`;
      } else {
        classHtml = '<span class="text-muted">未知</span>';
      }
      if (item.charRaceId) {
        const raceName = RACE_MAP[item.charRaceId] || item.charRaceName || '未知';
        const raceIcon = RACE_ICON_MAP[item.charRaceId] || '';
        raceHtml = `<div class="d-flex align-items-center class-race-container"><span>${escapeHtml(raceName)}</span>${raceIcon ? `<img src="${raceIcon}" alt="${raceName}" style="width:20px;height:20px;margin-left:5px;">` : ''}</div>`;
      } else {
        raceHtml = '<span class="text-muted">未知</span>';
      }
    } else {
      classHtml = '<span class="text-muted">-</span>';
      raceHtml = '<span class="text-muted">-</span>';
    }

    const tr = $(`<tr data-uid="${item.uid}">
      <td>${item.rank??''}</td>
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

  // initialize DataTable with initComplete callback
  try{
    dataTable = $('#leaderboard').DataTable({
      pageLength: 15,
      order:[[5,'desc']],
      columnDefs: [{ targets: 10, visible: false, searchable: true }],
      search: { smart: false },
      initComplete: function() {
        // 🔹 新增職業篩選 (S5+)
        if (season >= 5) {
          $('#classFilter').remove(); // 避免重複
          let classFilter = $('<select id="classFilter" class="form-select form-select-sm ms-2 w-auto"><option value="">全部職業</option></select>');
          $('#leaderboard_filter').append(classFilter);

          this.api().column(3).data().unique().sort().each(function(d){
            let tmp = $('<div>').html(d).text().trim();
            if (tmp && classFilter.find(`option[value="${tmp}"]`).length === 0) {
              classFilter.append(`<option value="${tmp}">${tmp}</option>`);
            }
          });

          classFilter.on('change', function(){
            let val = $.fn.dataTable.util.escapeRegex($(this).val());
            dataTable.column(3).search(val ? val : '', true, false).draw();
          });
        }
      }
    });
  } catch(e){ console.warn('DataTable init failed', e); }

  // bind click (use delegation)
  $('#leaderboard tbody').off('click', '.name-link').on('click', '.name-link', function(ev){
    const uid = $(this).data('uid');
    const entry = currentVisible.find(x=>x.uid === uid);
    if (entry) openModalFor(entry);
  });
}

export function clearTable() {
  if ($.fn.DataTable.isDataTable('#leaderboard')) {
    try { $('#leaderboard').DataTable().clear().destroy(); } catch(e){}
  }
  $('#leaderboard tbody').empty();
}


function openModalFor(entry) {
  $('#modalTitle').text(entry.isTeam? (entry.teamName || '隊伍') : (entry.charName || '角色'));
  $('#modalSub').text(entry.isTeam? `Realm: ${entry.teamRealm || '-' }  •  Rating: ${entry.rating}` : `Realm: ${entry.charRealm || '-'}  •  Rating: ${entry.rating}`);

  // crest
  const crestEl = document.getElementById('modalCrest');
  crestEl.style.background = '#222';
  if (entry.raw.team?.crest?.background?.color?.rgba) {
    const c = entry.raw.team.crest.background.color.rgba;
    crestEl.style.background = `rgba(${c.r},${c.g},${c.b},${c.a})`;
  }

  // populate members or single character
  const tbody = $('#memberTable tbody').empty();
  if (entry.isTeam && Array.isArray(entry.members) && entry.members.length>0){
    entry.members.forEach((m, idx)=>{
      const ch = m.character || {};
      const name = ch.name || '-';
      const clsId = ch.playable_class?.id ?? m.character?.playable_class?.id ?? null;
      const clsName = (clsId && CLASS_MAP[clsId]) ? CLASS_MAP[clsId] : (ch.playable_class?.name || '-');
      const raceId = ch.playable_race?.id ?? null;
      const raceName = raceId ? (RACE_MAP[raceId] || `Race ${raceId}`) : '-';
      const rating = m.rating || '-'; // FIX: Add rating variable here
      
      const stats = m.season_match_statistics || {};
      const played = safeNum(stats.played), won = safeNum(stats.won), lost = safeNum(stats.lost);
      const winp = played? (won/played*100).toFixed(1) : '0.0';
      
      // 職業顯示（含圖標和顏色）
      const classIcon = CLASS_ICON_MAP[clsId] || '';
      const classColor = CLASS_COLOR_MAP[clsId] || '#FFFFFF';
      const clsHtml = `<div class="d-flex align-items-center role-label class-race-container">
        <span style="color:${classColor}">${escapeHtml(clsName)}</span>
        ${classIcon ? `<img src="${classIcon}" alt="${clsName}" style="width:20px;height:20px;margin-left:5px;" onerror="this.style.display='none'">` : ''}
      </div>`;
      
      // 種族顯示（含圖標）
      const raceIcon = raceId ? (RACE_ICON_MAP[raceId] || '') : '';
      const raceHtml = `<div class="d-flex align-items-center class-race-container">
        <span>${escapeHtml(raceName)}</span>
        ${raceIcon ? `<img src="${raceIcon}" alt="${raceName}" style="width:20px;height:20px;margin-left:5px;" onerror="this.style.display='none'">` : ''}
      </div>`;
      
      const row = `<tr><td>${idx+1}</td><td>${escapeHtml(name)}</td><td>${clsHtml}</td><td>${raceHtml}</td><td>${rating}</td><td>${played}</td><td>${won}</td><td>${lost}</td><td>${winp}</td></tr>`;
      tbody.append(row);
    });
  } else {
    // single character entry (s5+)
    const name = entry.charName || entry.teamName || '-';
    const clsId = entry.charClassId || null;
    const clsName = (clsId && CLASS_MAP[clsId]) ? CLASS_MAP[clsId] : (entry.charClassName || '-');
    const raceId = entry.charRaceId || null;
    const raceName = raceId ? (RACE_MAP[raceId] || `Race ${raceId}`) : (entry.raw.character?.playable_race?.name || '-');
    
    // 職業顯示（含圖標和顏色）
    const classIcon = CLASS_ICON_MAP[clsId] || '';
    const classColor = CLASS_COLOR_MAP[clsId] || '#FFFFFF';
    const clsHtml = `<div class="d-flex align-items-center role-label class-race-container">
      <span style="color:${classColor}">${escapeHtml(clsName)}</span>
      ${classIcon ? `<img src="${classIcon}" alt="${clsName}" style="width:20px;height:20px;margin-left:5px;" onerror="this.style.display='none'">` : ''}
    </div>`;
    
    // 種族顯示（含圖標）
    const raceIcon = raceId ? (RACE_ICON_MAP[raceId] || '') : '';
    const raceHtml = `<div class="d-flex align-items-center class-race-container">
      <span>${escapeHtml(raceName)}</span>
      ${raceIcon ? `<img src="${raceIcon}" alt="${raceName}" style="width:20px;height:20px;margin-left:5px;" onerror="this.style.display='none'">` : ''}
    </div>`;
    
    const row = `<tr><td>1</td><td>${escapeHtml(name)}</td><td>${clsHtml}</td><td>${raceHtml}</td><td>${entry.rating}</td><td>${entry.played}</td><td>${entry.won}</td><td>${entry.lost}</td><td>${entry.winRate.toFixed(1)}</td></tr>`;
    tbody.append(row);
  }

  const modalEl = document.getElementById('teamModal');
  const bs = new bootstrap.Modal(modalEl);
  bs.show();
}