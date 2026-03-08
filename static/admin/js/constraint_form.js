(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    function show(el) { if (el) el.style.display = ''; }
    function hide(el) { if (el) el.style.display = 'none'; }

    function getConstraintType() {
        var s = document.querySelector('#id_constraint_type');
        return s ? s.value : '';
    }
    function getTargetType() {
        var s = document.querySelector('#id_target_type');
        return s ? s.value : '';
    }

    // -----------------------------------------------------------------------
    // Objetivo: mostrar solo el campo relevante (profesor/local/grupo/asignatura)
    // -----------------------------------------------------------------------
    function updateTargetFields() {
        var targetType = getTargetType();
        var fieldMap = {
            'PROFESSOR': 'professor',
            'ROOM':      'room',
            'GROUP':     'group',
            'SUBJECT':   'subject',
        };
        Object.values(fieldMap).forEach(function (field) {
            hide(document.querySelector('.field-' + field));
        });
        var active = fieldMap[targetType];
        if (active) show(document.querySelector('.field-' + active));
    }

    // -----------------------------------------------------------------------
    // Tipo de restricción: banner informativo + mostrar/ocultar Notas
    // -----------------------------------------------------------------------
    function updateHelpBanner() {
        var type = getConstraintType();
        var banner = document.getElementById('constraint-help-banner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'constraint-help-banner';
            banner.style.cssText = [
                'padding:10px 16px',
                'border-radius:0 0 8px 8px',
                'margin:0 0 12px 0',
                'font-size:0.84rem',
                'border-left:4px solid',
                'display:none',
                'line-height:1.5',
            ].join(';');
            var identSection = document.querySelector('.form-row.field-constraint_type, .field-constraint_type');
            if (identSection) identSection.after(banner);
        }

        var msgs = {
            'UNAVAILABILITY': {
                c: '#6366f1', bg: '#eef2ff',
                t: '📵 <strong>Indisponibilidad</strong>: el objetivo seleccionado no puede tener actividades en los días/turnos definidos. Define el patrón temporal en la sección de abajo.',
            },
            'TIME_SLOT_PREFERENCE': {
                c: '#0ea5e9', bg: '#f0f9ff',
                t: '🕐 <strong>Preferencia de franja</strong>: el objetivo prefiere clases de mañana o tarde. Selecciona la <em>Franja del día</em> en el patrón temporal.',
            },
            'ROOM_ASSIGNMENT': {
                c: '#10b981', bg: '#f0fdf4',
                t: '🏫 <strong>Local fijo</strong>: una asignatura se imparte siempre en un local concreto.<br>' +
                   'Elige <strong>Objetivo → Asignatura</strong>, selecciona la asignatura y el local.<br>' +
                   'En <em>Notas</em> puedes escribir <code>C</code>, <code>CP</code> o <code>L</code> para limitarlo a un tipo de actividad (vacío = todos los tipos).',
            },
        };

        var m = msgs[type];
        if (m) {
            banner.style.display    = 'block';
            banner.style.borderColor = m.c;
            banner.style.background  = m.bg;
            banner.style.color       = '#1a1a2e';
            banner.innerHTML         = m.t;
        } else {
            banner.style.display = 'none';
        }

        // Notas: solo visible para ROOM_ASSIGNMENT
        var notesRow = document.querySelector('.field-notes');
        if (notesRow) {
            notesRow.style.display = (type === 'ROOM_ASSIGNMENT') ? '' : 'none';
        }
    }

    // -----------------------------------------------------------------------
    // Patrón temporal de cada inline: ocultar campos irrelevantes
    // -----------------------------------------------------------------------
    function updatePatternRow(patternSelect) {
        if (!patternSelect) return;
        var pattern = patternSelect.value;
        var row = patternSelect.closest('.inline-related');
        if (!row) return;

        var constraintType = getConstraintType();

        // Campos semana
        var weekNumField      = row.querySelector('.field-week_numbers');
        var weekFromField     = row.querySelector('.field-week_from');
        var weekToField       = row.querySelector('.field-week_to');
        var weekParityField   = row.querySelector('.field-week_parity');
        var specificDatesField= row.querySelector('.field-specific_dates');
        var timeOfDayField    = row.querySelector('.field-time_of_day');

        [weekNumField, weekFromField, weekToField, weekParityField, specificDatesField].forEach(hide);

        if (pattern === 'WEEK_LIST')       show(weekNumField);
        if (pattern === 'WEEK_RANGE')    { show(weekFromField); show(weekToField); }
        if (pattern === 'WEEK_PARITY')     show(weekParityField);
        if (pattern === 'SPECIFIC_DATES')  show(specificDatesField);

        // time_of_day solo para TIME_SLOT_PREFERENCE
        if (timeOfDayField) {
            timeOfDayField.style.display = (constraintType === 'TIME_SLOT_PREFERENCE') ? '' : 'none';
        }
    }

    function updateAllPatternRows() {
        document.querySelectorAll('[id$="-pattern_type"]').forEach(updatePatternRow);
    }

    // -----------------------------------------------------------------------
    // Init
    // -----------------------------------------------------------------------
    document.addEventListener('DOMContentLoaded', function () {
        // Escuchar cambios en tipo de restricción
        var typeSelect = document.querySelector('#id_constraint_type');
        if (typeSelect) {
            typeSelect.addEventListener('change', function () {
                updateHelpBanner();
                updateAllPatternRows();
            });
        }

        // Escuchar cambios en tipo de objetivo
        var targetSelect = document.querySelector('#id_target_type');
        if (targetSelect) targetSelect.addEventListener('change', updateTargetFields);

        // Escuchar cambios en pattern_type de cualquier inline (incluyendo nuevos)
        document.addEventListener('change', function (e) {
            if (e.target && e.target.id && e.target.id.includes('-pattern_type')) {
                updatePatternRow(e.target);
            }
        });

        // Cuando Django añade un inline nuevo
        document.addEventListener('formset:added', function (e) {
            var ps = e.target && e.target.querySelector && e.target.querySelector('[id$="-pattern_type"]');
            if (ps) updatePatternRow(ps);
        });

        // Render inicial
        updateTargetFields();
        updateHelpBanner();
        updateAllPatternRows();
    });
})();