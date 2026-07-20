import React, { useMemo, useState } from 'react';

const formatCurrency = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value || 0);

const bandClassName = (band) => `band-badge band-${String(band || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

const getOwner = (resource) => resource?.tags?.owner || resource?.tags?.Owner || 'unassigned';

function ResourceTable({ resources }) {
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('score');
  const [direction, setDirection] = useState('desc');

  const filteredResources = useMemo(() => {
    const query = search.trim().toLowerCase();
    let filtered = resources;

    if (query) {
      filtered = resources.filter((resource) => {
        const haystack = [
          resource.name,
          resource.type,
          resource.resourceGroup,
          resource.region,
          getOwner(resource),
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return haystack.includes(query);
      });
    }

    const sorted = [...filtered].sort((a, b) => {
      const left = sortValue(a, sortBy);
      const right = sortValue(b, sortBy);

      if (left < right) {
        return direction === 'asc' ? -1 : 1;
      }
      if (left > right) {
        return direction === 'asc' ? 1 : -1;
      }
      return 0;
    });

    return sorted;
  }, [resources, search, sortBy, direction]);

  const handleSort = (column) => {
    if (column === sortBy) {
      setDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(column);
    setDirection(column === 'name' || column === 'type' || column === 'resourceGroup' ? 'asc' : 'desc');
  };

  return (
    <section className="table-panel">
      <div className="table-toolbar">
        <input
          className="search-input"
          type="search"
          placeholder="Search by name, type, owner, resource group, or region"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <div className="table-meta">
          Showing {filteredResources.length} of {resources.length} resources
        </div>
      </div>

      <div className="table-wrapper">
        <table className="resource-table">
          <thead>
            <tr>
              <SortableHeader label="Name" column="name" sortBy={sortBy} direction={direction} onSort={handleSort} />
              <SortableHeader label="Type" column="type" sortBy={sortBy} direction={direction} onSort={handleSort} />
              <SortableHeader label="Resource Group" column="resourceGroup" sortBy={sortBy} direction={direction} onSort={handleSort} />
              <SortableHeader label="Region" column="region" sortBy={sortBy} direction={direction} onSort={handleSort} />
              <SortableHeader label="Owner" column="owner" sortBy={sortBy} direction={direction} onSort={handleSort} />
              <SortableHeader label="Score" column="score" sortBy={sortBy} direction={direction} onSort={handleSort} />
              <SortableHeader label="Band" column="band" sortBy={sortBy} direction={direction} onSort={handleSort} />
              <SortableHeader label="Cost" column="cost" sortBy={sortBy} direction={direction} onSort={handleSort} />
              <th>Reasons</th>
            </tr>
          </thead>
          <tbody>
            {filteredResources.map((resource) => (
              <tr key={resource.id || `${resource.name}-${resource.resourceGroup}`}>
                <td>{resource.name}</td>
                <td>{resource.type}</td>
                <td>{resource.resourceGroup}</td>
                <td>{resource.region}</td>
                <td>{getOwner(resource)}</td>
                <td>{resource.score ?? 0}</td>
                <td>
                  <span className={bandClassName(resource.band)}>{resource.band || 'Unknown'}</span>
                </td>
                <td>{formatCurrency(resource.cost)}</td>
                <td className="reason-list">{(resource.reasons || []).join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SortableHeader({ label, column, sortBy, direction, onSort }) {
  const active = sortBy === column;
  return (
    <th onClick={() => onSort(column)}>
      {label} {active ? (direction === 'asc' ? '▲' : '▼') : '↕'}
    </th>
  );
}

function sortValue(resource, column) {
  switch (column) {
    case 'owner':
      return getOwner(resource).toLowerCase();
    case 'score':
      return resource.score || 0;
    case 'cost':
      return resource.cost || 0;
    default:
      return String(resource[column] || '').toLowerCase();
  }
}

export default ResourceTable;
