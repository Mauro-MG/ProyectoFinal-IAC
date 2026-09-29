// Comportamiento común del portal. Sin dependencias.
document.addEventListener('DOMContentLoaded', () => {
    // Menú en pantallas chicas
    const botonMenu = document.getElementById('boton-menu');
    const menu = document.getElementById('lateral') || document.getElementById('nav-publica');
    if (botonMenu && menu) {
        botonMenu.addEventListener('click', () => menu.classList.toggle('abierto'));
    }

    // Confirmación antes de acciones irreversibles: <form data-confirmar="¿Seguro?">
    document.querySelectorAll('form[data-confirmar]').forEach((form) => {
        form.addEventListener('submit', (e) => {
            if (!confirm(form.dataset.confirmar)) e.preventDefault();
        });
    });

    // Selects que envían su formulario al cambiar (filtros)
    document.querySelectorAll('select[data-autoenviar]').forEach((select) => {
        select.addEventListener('change', () => select.form.submit());
    });

    // Botón "usar mi ubicación" en formularios con latitud/longitud
    const botonUbicacion = document.getElementById('usar-ubicacion');
    if (botonUbicacion && navigator.geolocation) {
        botonUbicacion.addEventListener('click', () => {
            botonUbicacion.disabled = true;
            botonUbicacion.textContent = 'Obteniendo ubicación…';
            navigator.geolocation.getCurrentPosition((pos) => {
                document.getElementById('latitud').value = pos.coords.latitude.toFixed(7);
                document.getElementById('longitud').value = pos.coords.longitude.toFixed(7);
                botonUbicacion.textContent = 'Ubicación capturada';
            }, () => {
                botonUbicacion.disabled = false;
                botonUbicacion.textContent = 'No se pudo obtener; captúrala manualmente';
            }, { enableHighAccuracy: true, timeout: 10000 });
        });
    }

    // En "agregar productos": marcar la casilla al escribir en la fila
    document.querySelectorAll('tr[data-producto] input[type=number]').forEach((input) => {
        input.addEventListener('input', () => {
            const casilla = input.closest('tr').querySelector('input[type=checkbox]');
            if (casilla && input.value !== '') casilla.checked = true;
        });
    });
});
