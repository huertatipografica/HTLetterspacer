var elixir = require('laravel-elixir');

elixir.config.production = true;

elixir.config.jsOutput = 'js';
elixir.config.cssOutput = 'css';
elixir.config.assetsDir = '';
elixir.config.publicDir = '';

// console.log(elixir);

/*
 |--------------------------------------------------------------------------
 | Elixir Asset Management
 |--------------------------------------------------------------------------
 |
 | Elixir provides a clean, fluent API for defining some basic Gulp tasks
 | for your Laravel application. By default, we are compiling the Less
 | file for our application, as well as publishing vendor resources.
 |
 */

elixir(function(mix) {
    mix.sass('app.scss', 'css/app.css')
        .scripts([
            '../js-dev/vendor/*',
            '../js-dev/*.js'
        ], 'js/app.js')
});