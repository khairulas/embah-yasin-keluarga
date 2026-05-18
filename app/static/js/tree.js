// static/js/tree.js
(async function () {
  const container = document.getElementById('tree-container');
  const width = container.clientWidth;
  const height = container.clientHeight;

  // Fetch with auth
  const token = await firebase.auth().currentUser.getIdToken();
  const res = await fetch(`/api/tree/${window.TREE_FOCUS_ID}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) {
    container.innerHTML = '<div class="p-4 text-danger">Gagal memuatkan pohon.</div>';
    return;
  }
  const data = await res.json();

  const svg = d3.select('#tree-container').append('svg')
    .attr('width', width).attr('height', height);
  const g = svg.append('g');

  // Zoom/pan
  const zoom = d3.zoom().scaleExtent([0.2, 3]).on('zoom', (e) => g.attr('transform', e.transform));
  svg.call(zoom);
  document.getElementById('zoom-in').onclick  = () => svg.transition().call(zoom.scaleBy, 1.3);
  document.getElementById('zoom-out').onclick = () => svg.transition().call(zoom.scaleBy, 1 / 1.3);
  document.getElementById('zoom-fit').onclick = () => svg.transition().call(zoom.transform, d3.zoomIdentity);

  const NODE_W = 140, NODE_H = 50;
  const SPOUSE_GAP = 20;

  // ---------- Descendants tree (downward) ----------
  if (data.descendants) {
    const root = d3.hierarchy(data.descendants);
    const layout = d3.tree().nodeSize([NODE_W + SPOUSE_GAP, NODE_H * 2.5]);
    layout(root);

    // Shift down so the focus sits roughly in the upper-middle of the canvas
    const offsetX = width / 2;
    const offsetY = data.ancestors && data.ancestors.children.length
      ? height * 0.4 : height * 0.15;

    // Parent-child links
    g.append('g').selectAll('path')
      .data(root.links())
      .join('path')
      .attr('class', 'link')
      .attr('d', d => {
        const sx = d.source.x + offsetX, sy = d.source.y + offsetY;
        const tx = d.target.x + offsetX, ty = d.target.y + offsetY;
        const my = (sy + ty) / 2;
        return `M${sx},${sy} V${my} H${tx} V${ty}`;
      });

    // Nodes (focus + descendants) with spouses attached to the right
    const nodeGroups = g.append('g').selectAll('g')
      .data(root.descendants())
      .join('g')
      .attr('transform', d => `translate(${d.x + offsetX},${d.y + offsetY})`);

    nodeGroups.each(function (d) {
      renderPersonCard(d3.select(this), d.data, d.data.id === data.focus_id);

      // Spouses to the right of each person
      (d.data.spouses || []).forEach((spouse, i) => {
        const offset = (NODE_W + SPOUSE_GAP) * (i + 1);
        const spouseG = d3.select(this).append('g')
          .attr('transform', `translate(${offset}, 0)`);
        renderPersonCard(spouseG, spouse, false, true);

        // Spouse link (horizontal dashed)
        d3.select(this).insert('line', ':first-child')
          .attr('class', 'link spouse-link')
          .attr('x1', NODE_W / 2).attr('y1', 0)
          .attr('x2', offset - NODE_W / 2).attr('y2', 0);
      });
    });
  }

  // ---------- Ancestors tree (upward) ----------
  if (data.ancestors && data.ancestors.children && data.ancestors.children.length) {
    // Skip the focus node itself (it's already rendered as root of descendants).
    // Build a hierarchy from each parent independently and flip Y.
    const ancestorRoot = d3.hierarchy(data.ancestors);
    const layout = d3.tree().nodeSize([NODE_W + SPOUSE_GAP, NODE_H * 2.5]);
    layout(ancestorRoot);

    const offsetX = width / 2;
    const offsetY = height * 0.4;

    // Flip Y so parents go upward
    ancestorRoot.descendants().forEach(d => { d.y = -d.y; });

    g.append('g').selectAll('path')
      .data(ancestorRoot.links())
      .join('path')
      .attr('class', 'link')
      .attr('d', d => {
        const sx = d.source.x + offsetX, sy = d.source.y + offsetY;
        const tx = d.target.x + offsetX, ty = d.target.y + offsetY;
        const my = (sy + ty) / 2;
        return `M${sx},${sy} V${my} H${tx} V${ty}`;
      });

    // Skip rendering the focus node again (depth 0)
    g.append('g').selectAll('g')
      .data(ancestorRoot.descendants().filter(d => d.depth > 0))
      .join('g')
      .attr('transform', d => `translate(${d.x + offsetX},${d.y + offsetY})`)
      .each(function (d) {
        renderPersonCard(d3.select(this), d.data, false);
      });
  }

  // ---------- Helpers ----------
  function renderPersonCard(selection, person, isFocus, isSpouse = false) {
    const classes = ['node-card'];
    if (person.is_deceased) classes.push('deceased');
    if (isFocus) classes.push('focus');
    if (isSpouse) classes.push('spouse');

    const grp = selection.append('g')
      .attr('class', classes.join(' '))
      .on('click', () => { window.location.href = `/tree/${person.id}`; });

    grp.append('rect')
      .attr('x', -NODE_W / 2).attr('y', -NODE_H / 2)
      .attr('width', NODE_W).attr('height', NODE_H);

    // Truncate long names
    const displayName = person.name.length > 22
      ? person.name.slice(0, 20) + '…'
      : person.name;

    grp.append('text')
      .attr('class', 'node-name')
      .attr('text-anchor', 'middle')
      .attr('y', -6)
      .text(displayName)
      .append('title').text(person.name);  // full name on hover

    const dates = formatDates(person.birth_year, person.death_year, person.is_deceased);
    if (dates) {
      grp.append('text')
        .attr('class', 'node-dates')
        .attr('text-anchor', 'middle')
        .attr('y', 10)
        .text(dates);
    }
  }

  function formatDates(birth, death, isDeceased) {
    if (birth && death) return `b. ${birth} – d. ${death}`;
    if (birth && isDeceased) return `b. ${birth} – d. ?`;
    if (birth) return `b. ${birth}`;
    if (death) return `d. ${death}`;
    return '';
  }
})();
</script>